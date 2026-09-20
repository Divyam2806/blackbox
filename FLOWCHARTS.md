# BlackBox FW-Agent: System Architecture & Functional Flowcharts

This document provides comprehensive Mermaid flowcharts detailing the internal architecture of **BlackBox FW-Agent**, its simulation engines (Host-HAL, Wokwi CLI, Gazebo Sim), its MCP Server integration layer, and the step-by-step functional execution loop.

---

## 1. Complete Project System Architecture Flowchart

```mermaid
flowchart TD
    subgraph USER_INPUTS ["User & External Interfaces"]
        CLI["CLI Entry Point (src/fwagent/cli.py)"]
        MCP_CLIENT["MCP Clients (Claude Desktop, Antigravity, Cursor)"]
        FW_SOURCE["Firmware Source Code (.ino, .c, .cpp)"]
        SPEC_FILE["Specification Document (spec.md)"]
    end

    subgraph MCP_LAYER ["MCP Server Gateway (server/mcp_server.py)"]
        MCP_SERVER["MCPServer (Gazebo-FWAgent-Server)"]
        MCP_TOOLS["MCP Tools: start_gazebo, send_speed, run_fwagent, get_state"]
        MCP_RES["MCP Resources: gazebo://state, fwagent://latest_report"]
        MCP_SERVER --> MCP_TOOLS
        MCP_SERVER --> MCP_RES
    end

    subgraph ENGINE ["Orchestrator Core (src/fwagent/orchestrator.py)"]
        ST1["Stage 1: UNDERSTAND\n(static_parser.py & llm_analyzer.py)"]
        ST2["Stage 2: PLAN\n(Boundary, Fault, State, Dynamics Generators)"]
        ST3["Stage 3: EXECUTE\n(executor.py & scenario_compiler.py)"]
        ST4["Stage 4: OBSERVE & JUDGE\n(oracle.py & invariants.py)"]
        ST5["Stage 5: ADAPT\n(adaptive.py & bisection loop)"]
        ST6["Stage 6: EXPLAIN & REPORT\n(root_cause.py & html_reporter.py)"]
    end

    subgraph SIMULATION ["Dual-Engine Hardware Simulators"]
        HOST_HAL["Host-HAL Simulator\n(Virtual Arduino C++ Shim)"]
        WOKWI["Wokwi CLI Emulator\n(AVR Microchip Emulation)"]
        GAZEBO["Gazebo Sim 8.0 Backend\n(Physics Engine + GUI Window)"]
    end

    subgraph ARTIFACTS ["Output Reports & Data Artifacts"]
        HTML["report.html (Interactive Visual Dashboard)"]
        JSON_MODEL["firmware_model.json"]
        JSON_PLAN["test_plan.json"]
        JSON_RES["results.json"]
        JSON_FIND["findings.json"]
    end

    %% Connections
    CLI --> ENGINE
    MCP_CLIENT --> MCP_SERVER
    MCP_TOOLS --> ENGINE
    MCP_TOOLS --> GAZEBO

    FW_SOURCE --> ST1
    SPEC_FILE --> ST1

    ST1 -->|FirmwareModel| ST2
    ST2 -->|Test Plan| ST3
    ST3 -->|Drive Signals| SIMULATION
    SIMULATION -->|Serial Output & Pin Traces| ST4
    ST4 -->|Verdicts: PASS/FAIL/WARN| ST5
    ST5 -->|Adaptive Probe TestCases| ST3
    ST5 -->|Final Verdicts| ST6

    ST6 --> HTML
    ST6 --> JSON_MODEL
    ST6 --> JSON_PLAN
    ST6 --> JSON_RES
    ST6 --> JSON_FIND
```

---

## 2. Functional Flowchart: What the Main Project Does

```mermaid
flowchart TD
    subgraph STAGE1 ["1. UNDERSTAND (Static Code & Spec Parser)"]
        A["📄 Firmware Source (.ino) & Spec File"] --> S1_1["Parse Signal Pins (A0 Temp, D9 Fan, D13 LED)"]
        S1_1 --> S1_2["Extract Thresholds (30.0 C, 28.0 C) & Invariants"]
        S1_2 --> S1_OUT["FirmwareModel Schema"]
    end

    subgraph STAGE2 ["2. PLAN (Test Case Generation)"]
        S1_OUT --> S2_1["Boundary Value Analysis (29.9 C, 30.0 C, 30.1 C)"]
        S2_1 --> S2_2["Electrical Fault Injection (Wire Cut, Short to GND)"]
        S2_2 --> S2_3["Sensor Noise & Rapid Fluctuation Tests"]
        S2_3 --> S2_OUT["Generated Test Plan (20+ Cases)"]
    end

    subgraph STAGE3 ["3. EXECUTE (Hardware Simulation)"]
        S2_OUT --> S3_1{"Select Simulation Engine"}
        S3_1 -->|Host SIL| SIM1["Host-HAL Simulator (<0.3s)"]
        S3_1 -->|3D Physics| SIM2["Gazebo Sim 8.0 (3D + GUI Window)"]
        S3_1 -->|Hardware Emulation| SIM3["Wokwi CLI Chip Emulator"]
        SIM1 & SIM2 & SIM3 --> S3_OUT["Captured Logs & Voltage Traces"]
    end

    subgraph STAGE4 ["4. JUDGE & ADAPT (Rule Oracle & Closed-Loop Probing)"]
        S3_OUT --> S4_1["Rule Oracle Verification"]
        S4_1 --> S4_2["Issue Verdicts: PASS / FAIL / WARN"]
        S4_2 --> S4_DEC{"Ambiguous Results?"}
        S4_DEC -->|Yes| S4_ADAPT["Stage 5: Synthesize Adaptive Probe Tests"]
        S4_ADAPT --> S3_1
    end

    subgraph STAGE5 ["5. DIAGNOSE & REPORT (Root Cause & Endpoints)"]
        S4_DEC -->|No| S5_1["Line-Mapped Root Cause Explainer"]
        S5_1 --> S5_2["Generate C++ Code Fix Snippets"]
        S5_2 --> S5_OUT["📊 Interactive report.html + MCP Server Endpoints"]
    end
```
