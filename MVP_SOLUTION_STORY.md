# BlackBox FW-Agent: The Story of our Autonomous Embedded Verification MVP

> **A Narrative Technical Guide & Full MVP Architecture Overview**

---

## Prologue: The Embedded Developer’s Nightmare

Imagine you are an embedded systems engineer building firmware for an industrial cooling system, a medical device, or an autonomous drone. 

It is late Friday evening. The physical microcontroller board is connected to a maze of jumper wires, breadboards, logic analyzers, and oscilloscope probes. Your firmware controls a high-power cooling fan based on an analog temperature sensor. 

Suddenly, under high thermal stress, the fan fails to trigger in time. The chip overheats. 

*Why did it fail?*
* Was it a physical wire cut or open circuit?
* Was it an analog sensor short-circuit to GND?
* Was it a software bug in your C++ thermal cutoff loop at line 42?

To find out, traditional firmware developers are forced to manually cut wires, inject electrical noise with function generators, step through microchip registers line-by-line, and risk frying physical hardware. 

**Testing embedded software has historically been slow, hardware-bound, dangerous, and hard to automate.**

---

## Chapter 1: The Vision — Birth of BlackBox FW-Agent

We set out to build **BlackBox FW-Agent (`fwagent`)**: an autonomous AI-driven firmware testing agent and multi-engine simulation platform that eliminates the need for physical hardware during testing.

### What the Solution Does:
1. **Reads Raw Firmware Source & Microchip Binaries:** Supports `.ino`, `.cpp`, `.hex`, `.elf`, and `.uf2` files.
2. **Reverse-Engineers Hardware Schematics:** Reads C++/Arduino code AST and automatically infers MCU architecture (`ATmega328P`, `ESP32`, `STM32`), input sensors (`NTC Temp`, `HC-SR04 Ultrasonic`, `Soil Moisture`, `LDR Photoresistor`), and output actuators (`MOSFET Fan Motor`, `Servo Motor`, `Relay`, `Buzzer`).
3. **Runs Tri-Engine Virtual Simulations:** Executes firmware logic across Host Software-in-the-Loop (SIL), register-accurate Wokwi chip emulation, and Gazebo 3D physical world simulations.
4. **Injects Electrical & Boundary Faults:** Automatically simulates open circuits, GND shorts, sensor noise, and boundary edge cases without touching a single physical chip.
5. **Pinpoints Root Causes to Source Code Lines:** Evaluates signal traces against safety rules and highlights the exact line of C++ code that broke, generating drop-in code fixes.
6. **Exposes Model Context Protocol (MCP) Endpoints:** Operates locally or deploys remotely over HTTP/SSE so external AI agents (Claude, Cursor, ChatGPT) can invoke hardware simulations over the web.

---

## Chapter 2: The 6-Stage Autonomous Pipeline

When you feed firmware and specification requirements into `fwagent`, it executes a 6-stage autonomous verification loop:

```text
 Firmware Source (.ino / .cpp) + Specification Document (spec.md)
                                ↓
 ┌─────────────────────────────────────────────────────────────┐
 │ STAGE 1: UNDERSTAND                                         │
 │ - Parses C++ AST (tree-sitter-c) & pinout mapping          │
 │ - Extracts threshold values (e.g. 30.0 °C, 85.0 °C)         │
 └──────────────────────────────┬──────────────────────────────┘
                                ↓
 ┌─────────────────────────────────────────────────────────────┐
 │ STAGE 2: PLAN                                               │
 │ - Generates Boundary Value Analysis (BVA) test matrix       │
 │ - Injects electrical faults (Wire Cuts, GND Shorts, Noise)  │
 └──────────────────────────────┬──────────────────────────────┘
                                ↓
 ┌─────────────────────────────────────────────────────────────┐
 │ STAGE 3: EXECUTE                                            │
 │ - Host-HAL SIL (<0.3s local C++ execution)                  │
 │ - Wokwi CLI Microchip Register Emulation                   │
 │ - Gazebo 8.0 3D Physical World Telemetry                    │
 └──────────────────────────────┬──────────────────────────────┘
                                ↓
 ┌─────────────────────────────────────────────────────────────┐
 │ STAGE 4: JUDGE                                              │
 │ - Evaluates Rule Oracles against safety requirements        │
 │ - Yields verdicts: PASS, FAIL, WARN, or AMBIGUOUS           │
 └──────────────────────────────┬──────────────────────────────┘
                                ↓
 ┌─────────────────────────────────────────────────────────────┐
 │ STAGE 5: ADAPT                                              │
 │ - Dynamically bisects sensor input ranges upon ambiguity    │
 │ - Synthesizes Round 2 targeted probe test cases             │
 └──────────────────────────────┬──────────────────────────────┘
                                ↓
 ┌─────────────────────────────────────────────────────────────┐
 │ STAGE 6: EXPLAIN & EXPOSE                                   │
 │ - Maps defects directly to line numbers in .ino / .cpp      │
 │ - Generates AI code fixes, HTML reports, & MCP tool SSE API │
 └──────────────────────────────┴──────────────────────────────┘
```

---

## Chapter 3: Tri-Engine Hardware Simulation Layer

Different firmware projects require different levels of simulation fidelity. Our MVP implements a **Tri-Engine Simulation Layer**:

### 1. Host-HAL Software-in-the-Loop (SIL) Engine
* **How it works:** Uses virtual C++ hardware shims (`arduino_shim.h`) to compile firmware natively on the host operating system.
* **Speed:** Runs 35+ test cases in **under 0.3 seconds**.
* **Use case:** Instant local unit testing and rapid CI/CD test automation.

### 2. Wokwi Register-Accurate Chip Emulation Engine
* **How it works:** Executes compiled `.hex` or `.elf` microchip binaries on virtual AVR/ESP32 register emulators.
* **Fidelity:** Emulates exact hardware registers, interrupts, timers, and ADC sample clocks.
* **Use case:** Register-level validation before flashing physical microcontrollers.

### 3. Gazebo Sim 8.0 (Harmonic) 3D Physical Physics Engine
* **How it works:** Connects firmware IO signals directly to 3D physical worlds via ROS 2 / Gazebo transport topics (`/model/vehicle_blue/cmd_vel` & `/odometry`).
* **Fidelity:** Simulates gravity, wheel friction, momentum, obstacle collision, and 3D camera sensors.
* **Use case:** Autonomous mobile robots, drones, and robotic manipulators.

---

## Chapter 4: Dynamic Hardware Reverse-Engineering (The Wokwi Engine)

One of the project's standout breakthroughs is the **Automatic Hardware Reverse-Engineering Generator** ([src/fwagent/analyzer/wokwi_generator.py](file:///c:/Users/DR.RAJESH%20KUMAR/blackbox/src/fwagent/analyzer/wokwi_generator.py)).

### How it works:
1. **Code AST Analysis:** When a user uploads a new `.ino` or `.cpp` project, `StaticParser` parses signal declarations and pin assignments (`analogRead(A0)`, `digitalWrite(9, HIGH)`).
2. **Component Inferencing:** 
   * Name matches like `temp`, `thermal`, `lm35` $\rightarrow$ Inferred as **NTC Temperature Sensor** on pin `A0`.
   * Name matches like `moisture`, `soil`, `hum` $\rightarrow$ Inferred as **Soil Moisture Sensor** on pin `A1`.
   * Name matches like `fan`, `motor`, `pump` $\rightarrow$ Inferred as **PWM Cooling Fan / Motor** on pin `D9`.
   * Name matches like `relay`, `valve` $\rightarrow$ Inferred as **Relay Module** on pin `D2`.
3. **Wokwi `diagram.json` Synthesis:** Auto-synthesizes valid Wokwi circuit schematics with color-coded power (Red 5V), ground (Black GND), and logic signal wires (Green/Blue/Orange).
4. **Data-Driven Web Canvas:** The frontend HTML5 canvas reads this metadata and dynamically renders the exact MCU, sensors, actuators, pin traces, and stimulus sliders matching **THAT specific firmware**.

---

## Chapter 5: Model Context Protocol (MCP) & Remote Deployment

To make our solution accessible to AI agents across the globe, we built a native **Model Context Protocol (MCP) Server** ([server/mcp_server.py](file:///c:/Users/DR.RAJESH%20KUMAR/blackbox/server/mcp_server.py)).

### Local Execution Mode (`stdio`):
Connects directly to AI IDEs like Claude Desktop, Cursor, Antigravity, or Windsurf on the same machine.

### Remote Execution Mode (`--sse`):
Runs in HTTP Server-Sent Events (SSE) mode on port `8001`. When deployed to cloud platforms (Render, Railway, AWS) or exposed via `ngrok http 8001`, any AI agent anywhere on the web can invoke:

* 🛠️ `run_fwagent_suite`: Executes boundary & fault test suites on firmware.
* 🛠️ `start_gazebo_simulation`: Launches 3D physics worlds.
* 🛠️ `get_gazebo_state`: Reads vehicle pose, velocity, and sensor odometry.
* 📄 `gazebo://state`: Live resource streaming physics telemetry.
* 📄 `fwagent://latest_report`: Live resource providing latest test verdicts and findings.

---

## Chapter 6: The User Experience — A Walkthrough Story

Let's follow a developer named Alex using the MVP:

1. **Step 1: Selection & Startup**
   Alex opens the Web Dashboard at `http://127.0.0.1:8000`. Alex selects `cooling_fan_buggy` from the sample target menu (or uploads a custom `.ino` folder).

2. **Step 2: Triggering Autonomous Test Run**
   Alex clicks **Run tests**. The backend immediately launches the 6-stage verification loop. 

3. **Step 3: Real-Time SSE Terminal Stream**
   In real-time, the terminal logs stream events with side-gutter verdict indicators:
   * `00:00.120 [UNDERSTAND] Static AST parsed: MCU ATmega328P, Input A0 (Temp), Output D9 (Fan PWM), Output D13 (Error LED).`
   * `00:00.250 [PLAN] Generated 35 BVA test cases & 4 fault injection matrices.`
   * `00:00.410 [EXECUTE] Executing SIL test suite on Host-HAL...`
   * `00:00.680 [JUDGE] RULE-SAFETY-01: Thermal cutoff at 85.0°C... FAIL (Fan activation delayed +820ms).`

4. **Step 4: Interactive Hardware Canvas**
   Alex clicks **⚡ Wokwi Circuit Visualizer**. The dynamic canvas renders an Arduino Uno in the center, an NTC temperature sensor on the left, and a cooling fan motor + error LED on the right. Alex drags the temperature slider to 90°C and clicks **Wire Cut (Open)** to see how the system handles sensor failure in real time.

5. **Step 5: Line-Mapped Diagnostics & AI Code Fix**
   Alex scrolls down to the **Findings** section:
   * **Finding ID:** `[FINDING-01] Thermal Cutoff Delay Exceeds Safety Margin`
   * **Source Line:** `cooling_fan_buggy.ino:42`
   * **Likely Cause:** Hysteresis timer loop `delay(1000)` blocks interrupt servicing during thermal escalation.
   * **AI Suggested C++ Fix:**
     ```cpp
     // FIX: Replace blocking delay with non-blocking millis() check
     if (currentTemp >= 85.0 && (millis() - lastTriggerTime > 100)) {
         digitalWrite(FAN_PIN, HIGH);
     }
     ```

6. **Step 6: Report Generation & Export**
   Alex clicks **Open in new tab** or **Download report** to get a complete stand-alone `report.html` file with signal telemetry charts and audit metadata to share with the team.

---

## Epilogue: Summary of Value Delivered

| Metric | Traditional Breadboard Testing | BlackBox FW-Agent MVP |
| :--- | :--- | :--- |
| **Testing Speed** | Days / Weeks of manual wire setup | **< 0.3 seconds** per test suite |
| **Electrical Fault Testing** | High risk of destroying physical chips | **100% Virtual & Risk-Free** |
| **Bug Isolation** | Hours stepping through microchip registers | **Direct line-mapped C++ pinpointing** |
| **AI Integration** | None | **Native MCP Server (stdio + remote SSE)** |
| **Hardware Schematics** | Manual Fritzing / CAD drafting | **Automatic reverse-engineering from code** |

---

*BlackBox FW-Agent proves that embedded firmware verification can be fast, zero-hardware, fully automated, and powered by intelligent AI orchestration.*
