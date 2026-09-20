"""
Static Parser for Embedded Firmware (C/C++/Arduino sketches).
Extracts pin assignments, hardware primitives, threshold constants, line indices,
dynamic serial log regex patterns, and pin drive tracking without needing an LLM.

Backends (tried in order):
  1. tree-sitter-c  — full AST walk, works on any C/C++ firmware
  2. Regex          — legacy fallback for simple Arduino sketches
"""

import os
import re
from typing import Dict, List, Optional, Tuple
from fwagent.models import FirmwareModel, Signal, Threshold, ErrorPath, Rule
from fwagent.utils.lineindex import LineIndex

# Optional tree-sitter-c dependency
try:
    import tree_sitter_c as _tsc
    from tree_sitter import Language as _TSLanguage, Parser as _TSParser, Node as _TSNode
    _C_LANG = _TSLanguage(_tsc.language())
    _TS_AVAILABLE = True
except Exception:
    _TS_AVAILABLE = False

# Functions classified as firmware INPUT sources
_INPUT_CALL_FNS = frozenset({
    "analogRead", "digitalRead", "ping_cm", "sonar_ping_cm",
    "readTemperature", "readHumidity", "ultrasonic_get_distance",
})
# Functions classified as firmware OUTPUT sinks
_OUTPUT_CALL_FNS = frozenset({
    "digitalWrite", "analogWrite", "tone", "servo_set_angle",
})
# GPIO direction registrations
_PINMODE_FNS = frozenset({"pinMode"})
# Sensor object constructors
_SENSOR_CTOR_FNS = frozenset({"NewPing", "DHT", "Adafruit_BMP280"})


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
        if _TS_AVAILABLE:
            try:
                return self._parse_with_ast(content, line_index, firmware_name)
            except Exception:
                pass
        return self._parse_with_regex(content, line_index, firmware_name)

    def _parse_with_ast(self, content: str, line_index: LineIndex, firmware_name: str) -> FirmwareModel:
        model = FirmwareModel(firmware_name=firmware_name)
        parser = _TSParser(_C_LANG)
        tree = parser.parse(bytes(content, "utf-8"))
        root = tree.root_node

        defines: Dict[str, Tuple[str, int]] = {}
        float_constants: Dict[str, Tuple[float, int]] = {}

        def walk(node):
            yield node
            for child in node.children:
                yield from walk(child)

        for node in walk(root):
            if node.type == "preproc_def":
                name_node = node.child_by_field_name("name")
                val_node = node.child_by_field_name("value")
                if name_node and val_node:
                    n_str = name_node.text.decode("utf-8", errors="ignore").strip()
                    v_str = val_node.text.decode("utf-8", errors="ignore").strip()
                    line_no = node.start_point[0] + 1
                    defines[n_str] = (v_str, line_no)
                    try:
                        float_constants[n_str] = (float(v_str), line_no)
                    except ValueError:
                        pass
            elif node.type == "declaration":
                text = node.text.decode("utf-8", errors="ignore")
                line_no = node.start_point[0] + 1
                m = re.search(r"(?:const\s+)?(?:int|uint8_t|byte|float|double)\s+([A-Za-z0-9_]+)\s*=\s*([A-Za-z0-9_.]+)", text)
                if m:
                    var_name, var_val = m.group(1), m.group(2)
                    defines[var_name] = (var_val, line_no)
                    try:
                        float_constants[var_name] = (float(var_val), line_no)
                    except ValueError:
                        pass

        driven_pins = set()
        for node in walk(root):
            if node.type == "call_expression":
                fn_node = node.child_by_field_name("function")
                args_node = node.child_by_field_name("arguments")
                if not fn_node:
                    continue
                fn_name = fn_node.text.decode("utf-8", errors="ignore").strip()
                line_no = node.start_point[0] + 1
                
                if fn_name in _INPUT_CALL_FNS:
                    arg_text = args_node.text.decode("utf-8", errors="ignore").strip("()") if args_node else ""
                    pin_arg = arg_text.split(",")[0].strip() if arg_text else "input"
                    pin_val = defines.get(pin_arg, (pin_arg, line_no))[0]
                    sig_name = pin_arg.lower().replace("_pin", "")
                    if not any(s.name == sig_name for s in model.inputs):
                        model.inputs.append(
                            Signal(
                                name=sig_name,
                                kind="adc",
                                pin=pin_val,
                                unit="raw",
                                valid_range=(0.0, 1023.0),
                                line=line_no
                            )
                        )
                elif fn_name in _PINMODE_FNS and args_node:
                    arg_text = args_node.text.decode("utf-8", errors="ignore").strip("()")
                    parts = [p.strip() for p in arg_text.split(",")]
                    if len(parts) >= 2 and parts[1] == "OUTPUT":
                        pin_arg = parts[0]
                        pin_val = defines.get(pin_arg, (pin_arg, line_no))[0]
                        sig_name = pin_arg.lower().replace("_pin", "")
                        if not any(s.name == sig_name for s in model.outputs):
                            model.outputs.append(
                                Signal(
                                    name=sig_name,
                                    kind="gpio_out",
                                    pin=f"D{pin_val}" if str(pin_val).isdigit() else str(pin_val),
                                    line=line_no,
                                    driven=False
                                )
                            )
                elif fn_name in _OUTPUT_CALL_FNS:
                    arg_text = args_node.text.decode("utf-8", errors="ignore").strip("()") if args_node else ""
                    pin_arg = arg_text.split(",")[0].strip()
                    sig_name = fn_name if (pin_arg.isdigit() or pin_arg.lstrip("-").isdigit()) else pin_arg.lower().replace("_pin", "")
                    driven_pins.add(sig_name)
                    found = False
                    for s in model.outputs:
                        if s.name == sig_name or s.pin == pin_arg:
                            s.driven = True
                            found = True
                    if not found and sig_name:
                        model.outputs.append(
                            Signal(
                                name=sig_name,
                                kind="gpio_out",
                                pin=pin_arg,
                                line=line_no,
                                driven=True
                            )
                        )

            elif node.type == "assignment_expression":
                # AST Rule 1: Assignment left-side receives return value of a function call
                left_node = node.child_by_field_name("left")
                right_node = node.child_by_field_name("right")
                if left_node and right_node:
                    var_name = left_node.text.decode("utf-8", errors="ignore").strip()
                    line_no = node.start_point[0] + 1
                    var_lower = var_name.lower()
                    
                    # Ignore system timing / protocol / intermediate calculation variables
                    is_system_var = (
                        "time" in var_lower
                        or "timer" in var_lower
                        or "millis" in var_lower
                        or "micros" in var_lower
                        or "tick" in var_lower
                        or "stamp" in var_lower
                        or "pitch" in var_lower
                        or "trig" in var_lower
                        or var_lower in ("len", "n", "buf", "msg", "ubrr", "i", "j")
                    )

                    right_text = right_node.text.decode("utf-8", errors="ignore").strip()
                    is_timing_fn = any(tf in right_text.lower() for tf in ("millis", "micros", "delay", "mavlink"))

                    if not is_system_var and not is_timing_fn and right_node.type == "call_expression":
                        if not any(s.name == var_name for s in model.inputs):
                            is_cm = "ping" in right_text.lower() or "sonar" in right_text.lower() or "dist" in var_lower or "sensor" in var_lower
                            model.inputs.append(
                                Signal(
                                    name=var_name,
                                    kind="adc",
                                    pin=var_name.upper(),
                                    unit="cm" if is_cm else "raw",
                                    valid_range=(1.0, 70.0) if is_cm else (0.0, 1023.0),
                                    line=line_no
                                )
                            )

            elif node.type == "binary_expression":
                # AST Rule 3: Distinguish loop timeouts & timing checks from domain thresholds
                op_node = node.child_by_field_name("operator")
                left_node = node.child_by_field_name("left")
                right_node = node.child_by_field_name("right")
                if op_node and left_node and right_node:
                    op = op_node.text.decode("utf-8", errors="ignore")
                    if op in (">", ">=", "<", "<=", "==", "!="):
                        left = left_node.text.decode("utf-8", errors="ignore").strip()
                        right = right_node.text.decode("utf-8", errors="ignore").strip()
                        line_no = node.start_point[0] + 1

                        # Ignore timing comparison checks e.g. (millis() - HeartbeatTime) > 1000
                        left_lower = left.lower()
                        is_timing_check = (
                            "millis" in left_lower
                            or "micros" in left_lower
                            or "heartbeattime" in left_lower
                            or "time" in left_lower
                            or "timer" in left_lower
                            or "tick" in left_lower
                        )

                        # Check if inside loop and has mutation
                        is_in_loop = False
                        p = node.parent
                        while p:
                            if p.type in ("while_statement", "for_statement", "do_statement"):
                                is_in_loop = True
                                break
                            p = p.parent

                        has_mutation = left_node.type in ("update_expression", "unary_expression") or "++" in left or "--" in left

                        if is_in_loop and has_mutation:
                            model.error_paths.append(
                                ErrorPath(
                                    trigger="I/O loop timeout return 0",
                                    note=f"Loop timeout at line {line_no} returns failure state",
                                    line=line_no
                                )
                            )
                        elif not is_timing_check:
                            clean_left = re.sub(r"^[+-]+|[+-]+$", "", left).strip()
                            val = None
                            if right in float_constants:
                                val = float_constants[right][0]
                            else:
                                try:
                                    val = float(right)
                                except ValueError:
                                    pass
                            if val is not None:
                                model.thresholds.append(
                                    Threshold(signal=clean_left, op=op, value=val, line=line_no)
                                )

        for sig in model.outputs:
            if sig.pin in driven_pins or sig.name in driven_pins:
                sig.driven = True
            if not sig.driven:
                model.error_paths.append(
                    ErrorPath(
                        trigger="sensor fault / timeout",
                        handler=None,
                        note=f"Output {sig.name} ({sig.pin}) defined at line {sig.line} is never driven",
                        line=sig.line
                    )
                )

        regex_fallback = self._parse_with_regex(content, line_index, firmware_name)
        if not model.inputs:
            model.inputs = regex_fallback.inputs
        if not model.outputs:
            model.outputs = regex_fallback.outputs
        if not model.thresholds:
            model.thresholds = regex_fallback.thresholds
        model.log_patterns = regex_fallback.log_patterns
        model.rules = regex_fallback.rules

        return model

    def _parse_with_regex(self, content: str, line_index: LineIndex, firmware_name: str = "firmware") -> FirmwareModel:
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

        # 2. Extract inputs (analogRead, NewPing, ultrasonic, or sensor variables)
        analog_pattern = re.compile(r"analogRead\(\s*([A-Za-z0-9_]+)\s*\)")
        newping_pattern = re.compile(r"NewPing\s+([A-Za-z0-9_]+)")
        sensor_var_pattern = re.compile(r"(?:int|float|double)\s+([A-Za-z0-9_]*SENSOR[A-Za-z0-9_]*)\s*=")

        for line_no, line in enumerate(line_index.lines, start=1):
            line_clean = line.split("//")[0].strip()
            match_analog = analog_pattern.search(line_clean)
            if match_analog:
                pin_arg = match_analog.group(1)
                pin_str = pin_constants.get(pin_arg, (pin_arg, line_no))[0]
                sig_name = pin_arg.lower().replace("_pin", "")
                if not any(sig.name == sig_name for sig in model.inputs):
                    model.inputs.append(
                        Signal(
                            name=sig_name,
                            kind="adc",
                            pin=pin_str if str(pin_str).startswith("A") else f"A{pin_str}",
                            unit="raw",
                            valid_range=(0.0, 1023.0),
                            line=line_no,
                        )
                    )
            
            match_np = newping_pattern.search(line_clean)
            if match_np:
                np_name = match_np.group(1)
                if not any(sig.name == np_name for sig in model.inputs):
                    model.inputs.append(
                        Signal(
                            name=np_name,
                            kind="adc",
                            unit="cm",
                            valid_range=(1.0, 400.0),
                            line=line_no,
                        )
                    )

            match_svar = sensor_var_pattern.search(line_clean)
            if match_svar:
                sv_name = match_svar.group(1)
                if not any(sig.name == sv_name for sig in model.inputs):
                    model.inputs.append(
                        Signal(
                            name=sv_name,
                            kind="adc",
                            unit="cm",
                            valid_range=(0.0, 400.0),
                            line=line_no,
                        )
                    )

        # 3. Extract digital outputs (pinMode / digitalWrite / output variables)
        pinmode_pattern = re.compile(r"pinMode\(\s*([A-Za-z0-9_]+)\s*,\s*(OUTPUT|INPUT|INPUT_PULLUP)\s*\)")
        output_var_pattern = re.compile(r"(?:int|float|double)\s+([A-Za-z0-9_]*OUTPUT[A-Za-z0-9_]*)\s*=")

        output_pins: Dict[str, Tuple[str, int]] = {}
        for line_no, line in enumerate(line_index.lines, start=1):
            line_clean = line.split("//")[0].strip()
            match = pinmode_pattern.search(line_clean)
            if match:
                pin_arg, mode = match.group(1), match.group(2)
                pin_val = pin_constants.get(pin_arg, (pin_arg, line_no))[0]
                pin_id = f"D{pin_val}" if str(pin_val).isdigit() else str(pin_val)
                if mode == "OUTPUT":
                    output_pins[pin_arg] = (pin_id, line_no)

            match_outvar = output_var_pattern.search(line_clean)
            if match_outvar:
                ov_name = match_outvar.group(1)
                if not any(sig.name == ov_name for sig in model.outputs):
                    model.outputs.append(
                        Signal(
                            name=ov_name,
                            kind="gpio_out",
                            line=line_no,
                            driven=True,
                        )
                    )

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
            sig_name = pin_var.lower()
            if not any(sig.name == sig_name for sig in model.outputs):
                model.outputs.append(
                    Signal(
                        name=sig_name,
                        kind="gpio_out",
                        pin=pin_id,
                        line=def_line,
                        driven=is_driven,
                    )
                )

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
                            signal=var1,
                            op=op,
                            value=val,
                            line=line_no,
                        )
                    )

        # 5. DYNAMIC Serial Log Pattern Extraction
        # Scans Serial.print("KEY=") statements to dynamically assemble regex with named groups (?P<key>...)
        serial_print_str_pattern = re.compile(r'Serial\.print(?:ln)?\s*\(\s*"([^"]+)"\s*\)')
        
        extracted_keys = set()
        for line in line_index.lines:
            line_clean = line.split("//")[0].strip()
            str_match = serial_print_str_pattern.findall(line_clean)
            for s in str_match:
                keys = re.findall(r'([A-Za-z0-9_]+)\s*[:=]', s)
                for k in keys:
                    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', k).lower().strip('_')
                    if sanitized and not sanitized[0].isdigit():
                        extracted_keys.add((k, sanitized))

        if extracted_keys:
            patterns = []
            for orig_key, clean_key in sorted(extracted_keys, key=lambda x: x[0]):
                patterns.append(rf"{orig_key}=(?P<{clean_key}>[^\s,]+)")
            model.log_patterns = patterns
        else:
            in_sig = model.inputs[0].name.upper() if model.inputs else "TEMP"
            out_sig = model.outputs[0].name.upper() if model.outputs else "FAN"
            model.log_patterns = [rf"{in_sig}=(?P<{in_sig.lower()}>[-\d.]+) {out_sig}=(?P<{out_sig.lower()}>ON|OFF)"]


        # 6. Default invariants
        model.rules.extend([
            Rule(id="I1", text="fan/motor OFF at boot", source="invariant"),
            Rule(id="I2", text="implausible sensor values must not be accepted as valid", source="invariant"),
            Rule(id="I3", text="output must not chatter near threshold", source="invariant"),
        ])

        return model

