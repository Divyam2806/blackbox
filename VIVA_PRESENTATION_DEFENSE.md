# BlackBox FW-Agent: Invigilator Presentation & Defense Guide

> **VIVA Cheat Sheet, Project Defense & Counter-Question Answer Guide**

---

## 🎤 1. The 30-Second Pitch (What to say first)

> *"Good morning/afternoon. Our project is **BlackBox FW-Agent**, an Autonomous AI Verification Agent for Embedded Firmware.*
> 
> *Traditionally, testing firmware requires physical microcontrollers, breadboards, logic analyzers, and manually cutting wires to test hardware failures. Our system completely eliminates physical hardware during testing.*
> 
> *It reads raw C++/Arduino firmware, automatically reverse-engineers the hardware circuit schematic, executes combinatorial boundary and electrical fault tests (wire cuts, GND shorts) across a tri-engine simulation layer, and pinpoints software bugs directly to exact line numbers in the C++ source code with AI-generated fixes."*

---

## ⚙️ 2. How It Works Under the Hood (Step-by-Step)

When an invigilator asks *"How does your system actually test the firmware?"*, explain these **4 core steps**:

1. **Static AST Code Analysis & Reverse-Engineering:**
   * Uses a C++ AST parser (`tree-sitter-c`) to parse firmware files (`.ino`, `.cpp`).
   * Automatically infers the target MCU (`Arduino ATmega328P`, `ESP32`, `STM32`), input sensors (`NTC Temp`, `Ultrasonic`, `Soil Moisture`), output actuators (`Cooling Fan Motor`, `Relay`, `Servo`), and GPIO pin mappings.
   * Auto-synthesizes valid Wokwi `diagram.json` schematics and dynamic web UI canvas models.

2. **Automated Test Matrix Generation:**
   * **Boundary Value Analysis (BVA):** Generates test inputs right around safety thresholds (e.g., testing `29.9 °C`, `30.0 °C`, `30.1 °C`).
   * **Electrical Fault Injection:** Generates open-circuit (wire cut), short-to-GND, and sensor noise matrices.

3. **Multi-Engine Simulation Execution:**
   * Runs the firmware across 3 virtual simulation backends:
     * **Host-HAL C++ SIL:** Uses virtual C++ hardware shims (`arduino_shim.h`) to execute 35+ test cases natively in **< 0.3 seconds**.
     * **Wokwi CLI:** Register-accurate microchip chip emulation.
     * **Gazebo 8.0:** Real-time 3D physical world physics & vehicle odometry.

4. **Rule Oracle Evaluation & Line-Mapped Diagnostics:**
   * Evaluates hardware output observations against safety invariants.
   * If a safety requirement fails (e.g. thermal cutoff delay exceeds 100ms), it traces the execution stack back to the exact C++ source code line (e.g. `line 42: delay(1000)`) and outputs drop-in AI C++ code fixes.

---

## ⚔️ 3. Is It Better Than Wokwi / Tinkercad / Renode? YES!

When an invigilator asks *"Isn't Wokwi or Tinkercad already doing this? Why is your project better?"*, highlight these **5 Key Differentiators**:

| Feature | Wokwi / Tinkercad / Renode | BlackBox FW-Agent (Our Project) |
| :--- | :--- | :--- |
| **Testing Paradigm** | **Passive Manual GUI:** Human must click sliders and manually watch LEDs turn on/off. | **Active Autonomous AI Agent:** Automatically generates 35+ boundary & fault test cases and evaluates pass/fail rules without human intervention. |
| **Electrical Fault Injection** | Requires user to manually delete wires in the editor. | **Automated Fault Matrix:** Injects wire cuts, GND shorts, and sensor noise programmatically in code. |
| **Bug Isolation** | Shows signal values; user must debug C++ manually. | **Line-Mapped Root Cause Analysis:** Highlights exact line number in `.ino`/`.cpp` (e.g., `Line 42`) with AI fix code. |
| **Hardware Schematic Creation** | User must manually draw components and wire pins in GUI. | **Dynamic Reverse-Engineering:** Reads C++ code AST and auto-generates `diagram.json` schematics dynamically. |
| **AI Integration** | None. | **Native MCP Server:** Implements Model Context Protocol (stdio + HTTP/SSE) allowing remote AI agents (Claude, Cursor, ChatGPT) to control hardware simulations. |

---

## ❓ 4. Invigilator Counter-Questions & Answers (VIVA Defense)

### Q1: *"How do you simulate hardware without physical microcontrollers?"*
> **Answer:** *"We use a Software-in-the-Loop (SIL) architecture. We built a custom C++ hardware shim header (`arduino_shim.h`). When firmware calls `analogRead(A0)`, our wrapper feeds virtual sensor values from memory. When it calls `digitalWrite(9, HIGH)`, our wrapper captures the state change in memory. This lets us run tests natively on the CPU at 100x speed without physical chips."*

### Q2: *"What if Wokwi fails, is offline, or isn't installed on the evaluator's machine?"*
> **Answer:** *"We built a automatic fail-safe fallback architecture. If Wokwi CLI or Wokwi online simulator is unavailable, our system automatically falls back to our internal Host-HAL SIL engine (`host_hal.py`). It compiles the firmware natively on the host PC in under 0.3 seconds, guaranteeing tests always execute."*

### Q3: *"How does your system find the exact C++ source code line number of a bug?"*
> **Answer:** *"Our Static Parser constructs an Abstract Syntax Tree (AST) mapping variable names and hardware pin states back to line numbers in the `.ino` / `.cpp` file. When a Rule Oracle detects a safety violation during simulation (e.g., thermal trip delay), our diagnostic engine maps the timing anomaly back to the blocking statement (such as `delay(1000)` at line 42)."*

### Q4: *"What is MCP (Model Context Protocol) and why did you add it?"*
> **Answer:** *"MCP is an open standard created by Anthropic for connecting AI models safely to tools and APIs. By making our backend an MCP server (`server/mcp_server.py`), any external AI agent—like Claude Desktop, Cursor IDE, or a remote web LLM—can discover our simulation tools and execute hardware tests remotely over HTTP/SSE."*

### Q5: *"Can your project test other microcontrollers besides Arduino Uno?"*
> **Answer:** *"Yes. Our reverse-engineering engine auto-detects Arduino Uno (`ATmega328P`), ESP32 DevKit (`ESP32-D0WDQ6`), and STM32 Nucleo (`STM32C031C6`). The AST parser detects header includes (`WiFi.h`, `stm32f4xx_hal.h`) and GPIO naming conventions (`GPIO4`, `PA0`) to configure the target architecture."*

### Q6: *"Is your Gemini AI required for the test runner to work?"*
> **Answer:** *"No. The core testing engine, AST reverse-engineering parser, BVA test generator, and Rule Oracles work 100% offline deterministically. When an LLM API key is provided, Gemini enhances the system by generating natural language fix recommendations and reading high-level specification markdown documents."*

---

## 🏆 Summary Checklist for Your Demo

1. Open Web UI at `http://127.0.0.1:8000`.
2. Select target firmware (`cooling_fan_buggy`).
3. Click **Run tests** $\rightarrow$ Show real-time streaming SSE terminal logs.
4. Click **⚡ Wokwi Circuit Visualizer** $\rightarrow$ Demonstrate the reverse-engineered hardware canvas.
5. Scroll to **Findings** $\rightarrow$ Show the line-mapped C++ bug pinpointing (`Line 42`) and AI suggested code fix.
6. Click **Open in new tab** $\rightarrow$ Show the generated HTML verification report.
