"""
Static Parser for Embedded Firmware (C/C++/Arduino sketches).
Extracts pin assignments, hardware primitives, threshold constants, line indices,
and pin drive tracking without needing an LLM.
"""

import os
import re
from typing import Dict, List, Optional, Tuple
from fwagent.models import FirmwareModel, Signal, Threshold, ErrorPath, Rule
from fwagent.utils.lineindex import LineIndex


class StaticParser:
    def __init__(self):
        pass

    def parse_directory(self, firmware_dir: str) -> Tuple[FirmwareModel, LineIndex]:
        # Find main file (.ino, .c, .cpp)
        main_file = None
        for root, _, files in os.walk(firmware_dir):
            for file in files:
                if file.endswith((".ino", ".cpp", ".c")) and not file.startswith("sil_"):
                    main_file = os.path.join(root, file)
                    break
            if main_file:
                break

        if not main_file:
            raise FileNotFoundError(f"No firmware source file found in {firmware_dir}")

        with open(main_file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        line_index = LineIndex(content)
        model = self.parse_code(content, line_index, firmware_name=os.path.basename(firmware_dir))
        return model, line_index

    def parse_code(self, content: str, line_index: LineIndex, firmware_name: str = "firmware") -> FirmwareModel:
        model = FirmwareModel(firmware_name=firmware_name)

        # 1. Resolve constant pin assignments
        # e.g. const int TEMP_PIN = A0; const int FAN_PIN = 9;
        pin_constants: Dict[str, Tuple[str, int]] = {}
        const_pattern = re.compile(
            r"(?:const\s+)?(?:int|uint8_t|byte|float|double)\s+([A-Za-z0-9_]+)\s*=\s*([A-Za-z0-9_.]+);"
        )
        float_constants: Dict[str, Tuple[float, int]] = {}

        for line_no, line in enumerate(line_index.lines, start=1):
            line_clean = line.split("//")[0].strip()
            match = const_pattern.search(line_clean)
            if match:
                var_name, var_val = match.group(1), match.group(2)
                pin_constants[var_name] = (var_val, line_no)
                try:
                    float_constants[var_name] = (float(var_val), line_no)
                except ValueError:
                    pass

        # 2. Extract analog inputs (analogRead)
        analog_pattern = re.compile(r"analogRead\(\s*([A-Za-z0-9_]+)\s*\)")
        for line_no, line in enumerate(line_index.lines, start=1):
            line_clean = line.split("//")[0].strip()
            match = analog_pattern.search(line_clean)
            if match:
                pin_arg = match.group(1)
                pin_str = pin_constants.get(pin_arg, (pin_arg, line_no))[0]
                # Normalize pin (e.g. A0)
                if not any(sig.name == "temp" or sig.pin == pin_str for sig in model.inputs):
                    model.inputs.append(
                        Signal(
                            name="temp",
                            kind="adc",
                            pin=pin_str if pin_str.startswith("A") else f"A{pin_str}",
                            unit="C",
                            valid_range=(0.0, 100.0),
                            line=line_no,
                        )
                    )

        # 3. Extract digital outputs (pinMode / digitalWrite)
        pinmode_pattern = re.compile(r"pinMode\(\s*([A-Za-z0-9_]+)\s*,\s*(OUTPUT|INPUT|INPUT_PULLUP)\s*\)")
        output_pins: Dict[str, Tuple[str, int]] = {}
        for line_no, line in enumerate(line_index.lines, start=1):
            line_clean = line.split("//")[0].strip()
            match = pinmode_pattern.search(line_clean)
            if match:
                pin_arg, mode = match.group(1), match.group(2)
                pin_val = pin_constants.get(pin_arg, (pin_arg, line_no))[0]
                pin_id = f"D{pin_val}" if pin_val.isdigit() else pin_val
                if mode == "OUTPUT":
                    output_pins[pin_arg] = (pin_id, line_no)

        # Track which outputs are actually driven with digitalWrite
        digital_write_pattern = re.compile(r"digitalWrite\(\s*([A-Za-z0-9_]+)\s*,")
        driven_pins = set()
        for line_no, line in enumerate(line_index.lines, start=1):
            line_clean = line.split("//")[0].strip()
            match = digital_write_pattern.search(line_clean)
            if match:
                pin_arg = match.group(1)
                driven_pins.add(pin_arg)

        for pin_var, (pin_id, def_line) in output_pins.items():
            is_driven = pin_var in driven_pins
            sig_name = "fan" if "FAN" in pin_var.upper() else ("err_led" if "ERR" in pin_var.upper() else pin_var.lower())
            model.outputs.append(
                Signal(
                    name=sig_name,
                    kind="gpio_out",
                    pin=pin_id,
                    line=def_line,
                    driven=is_driven,
                )
            )

            # If an output pin is never written, flag an unhandled error path / warning
            if not is_driven:
                model.error_paths.append(
                    ErrorPath(
                        trigger="sensor fault / timeout",
                        handler=None,
                        note=f"Output {pin_var} ({pin_id}) defined at line {def_line} is never driven by digitalWrite",
                        line=def_line,
                    )
                )

        # 4. Extract threshold comparison rules & constants
        # e.g. if (t >= THRESH_C) or if (t >= 30.0)
        thresh_pattern = re.compile(r"if\s*\(\s*([A-Za-z0-9_.]+)\s*(>=|>|<=|<|==|!=)\s*([A-Za-z0-9_.]+)\s*\)")
        for line_no, line in enumerate(line_index.lines, start=1):
            line_clean = line.split("//")[0].strip()
            match = thresh_pattern.search(line_clean)
            if match:
                var1, op, var2 = match.group(1), match.group(2), match.group(3)
                val = None
                if var2 in float_constants:
                    val = float_constants[var2][0]
                else:
                    try:
                        val = float(var2)
                    except ValueError:
                        pass

                if val is not None:
                    model.thresholds.append(
                        Threshold(
                            signal="temp",
                            op=op,
                            value=val,
                            line=line_no,
                        )
                    )

        # 5. Extract Serial log patterns
        # Look for Serial.print("T="); ... Serial.print(" FAN="); ...
        if "Serial.print" in content or "Serial.println" in content:
            model.log_patterns.append(r"T=(?P<t>[-\d.]+) FAN=(?P<fan>ON|OFF)")

        # 6. Default invariants
        model.rules.extend([
            Rule(id="I1", text="fan/motor OFF at boot", source="invariant"),
            Rule(id="I2", text="implausible sensor values must not be accepted as valid", source="invariant"),
            Rule(id="I3", text="output must not chatter near threshold", source="invariant"),
        ])

        return model
