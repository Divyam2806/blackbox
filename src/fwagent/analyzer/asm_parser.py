"""
Universal Assembly Firmware Parser.
Generically parses assembly code (.asm, .s, .S, .inc) across architectures
(8085, AVR assembly, ARM assembly, RISC-V, PIC, x86) to extract hardware I/O ports,
register thresholds, memory-mapped peripherals, and halt/stall paths.
"""

import re
from typing import Dict, List, Tuple
from fwagent.models import FirmwareModel, Signal, Threshold, ErrorPath, Rule
from fwagent.utils.lineindex import LineIndex


class UniversalAsmParser:
    """
    Generic Static Analyzer for Embedded Assembly Programs.
    """

    def parse_code(self, content: str, line_index: LineIndex, firmware_name: str = "firmware_asm") -> FirmwareModel:
        model = FirmwareModel(firmware_name=firmware_name)

        # 1. Extract EQU / Constants / Definitions
        equates: Dict[str, Tuple[str, int]] = {}
        equ_pattern = re.compile(
            r"(?:([A-Za-z0-9_.]+)\s+(?:EQU|\.equ|\.set)\s+([A-Za-z0-9_.]+))|(?:#define\s+([A-Za-z0-9_.]+)\s+([A-Za-z0-9_.]+))",
            re.IGNORECASE
        )

        for line_no, line in enumerate(line_index.lines, start=1):
            line_clean = line.split(";")[0].split("//")[0].strip()
            match = equ_pattern.search(line_clean)
            if match:
                k = match.group(1) or match.group(3)
                v = match.group(2) or match.group(4)
                if k and v:
                    equates[k.strip().upper()] = (v.strip().upper(), line_no)

        # 2. Universal Assembly I/O Patterns
        # Input instructions (IN, LDR, LDA, MOV from M, READ, SBIS, SBIC)
        in_patterns = [
            re.compile(r"\b(?:IN|READ|GET|SENSE)\s+([A-Za-z0-9_]+)", re.IGNORECASE),
            re.compile(r"\bIN\s+[A-Za-z0-9_]+\s*,\s*\(?([A-Za-z0-9_]+)\)?", re.IGNORECASE),
            re.compile(r"\b(?:LDR|MOV|LDA)\s+[A-Za-z0-9_]+\s*,\s*\[?\s*(PORT[A-Z0-9_]*|PIN[A-Z0-9_]*|ADC[A-Z0-9_]*|SENSOR[A-Z0-9_]*|0x[0-9A-FA-F]+|[0-9]+H?)\s*\]?", re.IGNORECASE),
            re.compile(r"\bLDA\s+([0-9A-FA-F]+H?)", re.IGNORECASE),
        ]

        # Output instructions (OUT, STR, STA, WRITE, SBI, CBI, MOV to PORT/PIN)
        out_patterns = [
            re.compile(r"\b(?:OUT|WRITE|DRIVE|SET)\s+([A-Za-z0-9_]+)", re.IGNORECASE),
            re.compile(r"\bOUT\s+\(?([A-Za-z0-9_]+)\)?\s*,\s*[A-Za-z0-9_]+", re.IGNORECASE),
            re.compile(r"\b(?:STR|MOV|STA)\s+\[?\s*(PORT[A-Z0-9_]*|PIN[A-Z0-9_]*|PWM[A-Z0-9_]*|ACTUATOR[A-Z0-9_]*|LED[A-Z0-9_]*|SERVO[A-Z0-9_]*|0x[0-9A-FA-F]+|[0-9]+H?)\s*\]?\s*,\s*[A-Za-z0-9_]+", re.IGNORECASE),
            re.compile(r"\bSTA\s+([0-9A-FA-F]+H?)", re.IGNORECASE),
        ]

        # Memory pointer address tracking (e.g. LXI H, 2501H)
        current_mem_ptr = None
        lxi_h_pattern = re.compile(r"\bLXI\s+H\s*,\s*([0-9A-FA-F]+H?)", re.IGNORECASE)
        mov_mem_in_pattern = re.compile(r"\bMOV\s+[A-Z]\s*,\s*M\b", re.IGNORECASE)

        for line_no, line in enumerate(line_index.lines, start=1):
            line_clean = line.split(";")[0].split("//")[0].strip()
            if not line_clean or line_clean.startswith("."):
                continue

            match_lxi = lxi_h_pattern.search(line_clean)
            if match_lxi:
                current_mem_ptr = match_lxi.group(1).upper()

            match_mov_m = mov_mem_in_pattern.search(line_clean)
            if match_mov_m and current_mem_ptr:
                sig_id = f"mem_{current_mem_ptr.lower().replace('h', '')}"
                if not any(s.name == sig_id for s in model.inputs):
                    model.inputs.append(
                        Signal(
                            name=sig_id,
                            kind="adc",
                            pin=f"Addr_{current_mem_ptr}",
                            unit="raw",
                            valid_range=(0.0, 255.0),
                            line=line_no
                        )
                    )

            # Check Inputs
            for pat in in_patterns:
                match = pat.search(line_clean)
                if match:
                    port_arg = match.group(1).upper()
                    port_val = equates.get(port_arg, (port_arg, line_no))[0]
                    sig_name = port_val.lower().replace("0x", "").replace("h", "")
                    sig_id = f"in_{sig_name}"
                    if not any(s.name == sig_id or s.pin == port_val for s in model.inputs):
                        model.inputs.append(
                            Signal(
                                name=sig_id,
                                kind="adc" if "adc" in port_arg.lower() or "sensor" in port_arg.lower() else "digital_in",
                                pin=f"Port_{port_val}",
                                unit="raw",
                                valid_range=(0.0, 255.0),
                                line=line_no
                            )
                        )
                    break

        # Check Outputs & Modified Registers
        mov_a_pattern = re.compile(r"\bMOV\s+A\s*,\s*([A-Z0-9_]+)", re.IGNORECASE)
        inr_dcr_pattern = re.compile(r"\b(?:INR|DCR|ADD|SUB|ADI|SUI)\s+([A-E|H|L])\b", re.IGNORECASE)
        for line_no, line in enumerate(line_index.lines, start=1):
            line_clean = line.split(";")[0].split("//")[0].strip()
            if not line_clean or line_clean.startswith("."):
                continue

            for pat in out_patterns:
                match = pat.search(line_clean)
                if match:
                    port_arg = match.group(1).upper()
                    port_val = equates.get(port_arg, (port_arg, line_no))[0]
                    sig_name = port_val.lower().replace("0x", "").replace("h", "")
                    sig_id = f"out_{sig_name}"
                    if not any(s.name == sig_id or s.pin == port_val for s in model.outputs):
                        model.outputs.append(
                            Signal(
                                name=sig_id,
                                kind="gpio_out",
                                pin=f"Port_{port_val}",
                                line=line_no,
                                driven=True
                            )
                        )
                    break

            match_mov_a = mov_a_pattern.search(line_clean)
            if match_mov_a:
                src_reg = match_mov_a.group(1).upper()
                if src_reg != "M" and not any(s.name == "acc_result" for s in model.outputs):
                    model.outputs.append(
                        Signal(
                            name="acc_result",
                            kind="gpio_out",
                            pin=f"Reg_A (from {src_reg})",
                            line=line_no,
                            driven=True
                        )
                    )

            match_inr = inr_dcr_pattern.search(line_clean)
            if match_inr:
                reg_name = match_inr.group(1).upper()
                sig_id = f"reg_{reg_name.lower()}"
                if not any(s.name == sig_id for s in model.outputs):
                    model.outputs.append(
                        Signal(
                            name=sig_id,
                            kind="gpio_out",
                            pin=f"Reg_{reg_name}",
                            line=line_no,
                            driven=True
                        )
                    )

        # 3. Universal Comparison / Threshold Extraction (CPI, CMP, COMP, SUB, TEQ, MVI)
        cmp_pattern = re.compile(
            r"\b(?:CPI|CMP|COMPARE|SUB|SUBS|TEQ|TST)\s+(?:[A-Za-z0-9_]+\s*,\s*)?([A-Za-z0-9_.]+)",
            re.IGNORECASE
        )
        mvi_pattern = re.compile(r"\bMVI\s+[A-Z]\s*,\s*([0-9A-FA-F]+H?)", re.IGNORECASE)

        for line_no, line in enumerate(line_index.lines, start=1):
            line_clean = line.split(";")[0].split("//")[0].strip()
            match = cmp_pattern.search(line_clean)
            if match:
                val_str = match.group(1).upper()
                val_num = self._parse_num(val_str)
                if val_num is not None:
                    model.thresholds.append(
                        Threshold(
                            signal=model.inputs[0].name if model.inputs else "input_port",
                            op=">=",
                            value=float(val_num),
                            line=line_no
                        )
                    )
            match_mvi = mvi_pattern.search(line_clean)
            if match_mvi:
                val_str = match_mvi.group(1).upper()
                val_num = self._parse_num(val_str)
                if val_num is not None and val_num > 0 and not model.thresholds:
                    model.thresholds.append(
                        Threshold(
                            signal=model.inputs[0].name if model.inputs else "input_port",
                            op="<=",
                            value=float(val_num),
                            line=line_no
                        )
                    )

        # 4. Universal Halt & Infinite Loop Extraction (HLT, HALT, WFI, JMP $, rjmp .)
        halt_pattern = re.compile(r"\b(?:HLT|HALT|WFI)\b|JMP\s+\$|rjmp\s+\.", re.IGNORECASE)
        for line_no, line in enumerate(line_index.lines, start=1):
            line_clean = line.split(";")[0].split("//")[0].strip()
            if halt_pattern.search(line_clean):
                model.error_paths.append(
                    ErrorPath(
                        trigger="assembly halt / infinite spin",
                        note=f"Assembly halt at line {line_no}",
                        line=line_no
                    )
                )

        # Invariant Rules
        model.rules.extend([
            Rule(id="I1", text="Outputs 00H (OFF) at initialization", source="invariant"),
            Rule(id="I2", text="Invalid sensor input must drive error indicator or fault branch", source="invariant"),
            Rule(id="I3", text="Output must remain stable near comparison threshold", source="invariant"),
        ])

        return model

    def _parse_num(self, s: str) -> int:
        s = s.strip().upper()
        if s.endswith("H"):
            try:
                return int(s[:-1], 16)
            except ValueError:
                return None
        if s.startswith("0X"):
            try:
                return int(s[2:], 16)
            except ValueError:
                return None
        try:
            return int(s)
        except ValueError:
            return None
