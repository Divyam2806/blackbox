# BlackBox FW-Agent: Complete Solution Brief for NotebookLM & Presentation Generation

---

## 1. Executive Summary & Value Proposition

* **Project Title:** BlackBox FW-Agent (`fwagent`)
* **Subtitle:** Autonomous Embedded Firmware Verification, Hardware Reverse-Engineering, & Multi-Backend Simulation Engine
* **One-Line Pitch:** An AI-powered testing agent that reads embedded C++/Arduino firmware, automatically reverse-engineers hardware circuit models (Wokwi `diagram.json`), runs combinatorial boundary and fault tests across physical simulators (Host SIL, Wokwi CLI, Gazebo Sim 3D), pinpoints bugs to exact C++ source lines, and exposes real-time MCP server endpoints.

---

## 2. Problem Statement vs. Solution

### The Embedded Firmware Crisis
1. **Slow & Hardware-Bound:** Firmware testing traditionally requires physical microcontrollers, breadboards, logic analyzers, and manual wire cutting.
2. **Hard-to-Reproduce Faults:** Electrical noise, open-circuit sensor wire cuts, and short-to-GND faults are difficult to inject safely without destroying physical chips.
3. **Ambiguous Root Causes:** When a physical fan or motor behaves unexpectedly, developers must spend hours stepping through microchip registers to find which line of C++ code broke.

### Our Automated Solution
* **Zero-Hardware Testing:** Compiles and runs firmware in virtual software-in-the-loop (SIL) and chip emulator backends.
* **Automated Hardware Model Generation:** Analyzes machine instructions / C++ code to infer MCU architecture, GPIO pinouts, and peripheral sensors/actuators, synthesizing official Wokwi `diagram.json` and `wokwi.toml` circuit topology.
* **Line-Mapped Root Cause Analysis:** Evaluates test results against safety rules and pinpoints defects directly to line numbers in `.ino` / `.cpp` source files with AI-suggested code fixes.

---

## 3. The 6-Stage Autonomous Pipeline Architecture

```text
Firmware Source (.ino / .cpp) + Spec Document (spec.md)
   ↓
[Stage 1: UNDERSTAND]  → AST parsing (tree-sitter-c), signal pin mapping, threshold extraction
   ↓
[Stage 2: PLAN]        → Boundary Value Analysis (BVA), equivalence partitioning, fault injection
   ↓
[Stage 3: EXECUTE]     → Multi-engine execution (Host SIL <0.3s, Wokwi CLI, Gazebo 3D GUI)
   ↓
[Stage 4: JUDGE]       → Rule Oracle verification against safety invariants (PASS / FAIL / WARN)
   ↓
[Stage 5: ADAPT]       → Closed-loop adaptive probe synthesis & bisection for boundary limits
   ↓
[Stage 6: EXPLAIN]     → Line-mapped C++ bug isolation, AI code fix generation, HTML report & MCP server
```

---

## 4. Key Technological Innovations

### 1. Reverse-Engineered Hardware Model Generation
* Reads `.ino`, `.cpp`, `.hex`, or `.elf` files.
* Detects MCU target (`Arduino Uno ATmega328P`, `ESP32 DevKit`, `STM32 Nucleo`).
* Infers input sensors (`NTC Temp`, `HC-SR04 Ultrasonic`, `Potentiometer`, `LDR Photoresistor`).
* Infers output actuators (`MOSFET Fan Motor`, `Servo Motor`, `LED + Resistor`, `Relay`, `Buzzer`).
* Auto-synthesizes valid Wokwi `diagram.json` layout with color-coded power, GND, and signal wiring.

### 2. Tri-Engine Hardware Simulation Layer
* **Host-HAL SIL:** Virtual C++ Arduino hardware shim. Runs 20+ test cases in under 0.3 seconds.
* **Wokwi CLI Hardware Emulation:** Executes compiled microchip binaries (`.hex`/`.elf`) on virtual register-level AVR/ESP32 emulators.
* **Gazebo Sim 8.0 (Harmonic):** Couples firmware signals to 3D physics worlds with a live 2D/3D viewport canvas GUI and real-time odometry telemetry.

### 3. Closed-Loop Adaptive Testing & Bisection
* Automatically detects ambiguous boundary test outcomes in Round 1.
* Dynamically synthesizes Round 2 targeted probe test cases.
* Bisects input range to determine exact trusted sensor ADC count windows (e.g. `5..1018` ADC counts).

### 4. Model Context Protocol (MCP) Server Integration
* Implements standard MCP Server (`server/mcp_server.py`) using `mcp.server.mcpserver.MCPServer`.
* Exposes tools: `start_gazebo_simulation`, `stop_gazebo_simulation`, `send_vehicle_speed`, `get_gazebo_state`, `list_gazebo_topics`, `run_fwagent_suite`.
* Exposes resources: `gazebo://state` (live physics state), `fwagent://latest_report` (verdicts & findings).

---

## 5. Slide-by-Slide Outline for PPT Generation

### Slide 1: Title Slide
* **Title:** BlackBox FW-Agent
* **Subtitle:** Autonomous Embedded Firmware Verification & Hardware Reverse-Engineering Engine
* **Footer:** AI-Driven Software-in-the-Loop & Multi-Backend Simulation

### Slide 2: The Challenge of Embedded Quality
* Manual hardware breadboard testing is a bottleneck.
* Inability to test electrical faults (wire cuts, GND shorts) without risk of hardware damage.
* Tracing firmware bugs from physical pin behaviors back to C++ source lines is time-consuming.

### Slide 3: The Solution Overview
* Autonomous end-to-end testing pipeline.
* Zero physical hardware required.
* Dynamic reverse-engineering of hardware models from raw code.
* Instant line-mapped bug pinpointing & AI fix generation.

### Slide 4: Core Architecture: The 6-Stage Loop
* **Understand:** Static AST code parsing & pinout extraction.
* **Plan:** Automated BVA, fault injection, & edge-case test planning.
* **Execute:** Multi-engine simulation execution.
* **Judge:** Automated Rule Oracle verification.
* **Adapt:** Closed-loop adaptive probing.
* **Explain:** Line-mapped source debugging & reporting.

### Slide 5: Innovation 1: Reverse-Engineered Wokwi Circuits
* Analyzes firmware binaries & code.
* Automatically infers MCU chip type, sensor inputs, and output actuators.
* Synthesizes official Wokwi `diagram.json` and `wokwi.toml` files for interactive web simulation.

### Slide 6: Innovation 2: Tri-Engine Simulation Layer
* **Host-HAL SIL:** Ultra-fast (<0.3s) local C++ execution.
* **Wokwi CLI:** Register-accurate microcontroller chip emulation.
* **Gazebo Sim 8.0:** Real-time 3D physical world & vehicle odometry simulation.

### Slide 7: Innovation 3: Closed-Loop Adaptive Testing
* Self-correcting test generation.
* Dynamically bisects sensor boundary conditions upon ambiguous results.
* Guarantees precise trusted sensor operating windows.

### Slide 8: Innovation 4: Line-Mapped Diagnostics & Reporting
* Maps failed test verdicts directly to `.ino` / `.cpp` source line numbers.
* Generates drop-in C++ fix snippets.
* Builds interactive HTML dashboards with real-time signal timeline charts.

### Slide 9: Innovation 5: Model Context Protocol (MCP) Server
* Native MCP Server integration for AI tools & client assistants (Claude Desktop, Cursor, Antigravity).
* Exposes live simulation control tools and telemetry resources via standard JSON-RPC endpoints.

### Slide 10: Value & Impact Summary
* **100x Faster:** Test execution time reduced from hours to seconds.
* **100% Coverage:** Covers normal, boundary, and extreme electrical fault conditions.
* **Zero Hardware Cost:** Complete virtual testing environment.

---

## 6. Key Terminology Glossary for NotebookLM

* **Software-in-the-Loop (SIL):** Compiling C++ firmware logic natively on the host PC using virtual Arduino shims for sub-second execution.
* **Boundary Value Analysis (BVA):** Generating test inputs right at, just below, and just above threshold boundaries (e.g. 29.9 °C, 30.0 °C, 30.1 °C).
* **Fault Injection:** Simulating electrical failures such as open circuits (wire cuts) or short circuits to GND.
* **Rule Oracle:** An automated verifier that evaluates hardware signal observations against specification requirements and safety invariants.
* **Model Context Protocol (MCP):** An open standard for connecting AI assistants safely to local tools, APIs, and simulation servers.
