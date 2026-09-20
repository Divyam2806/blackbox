# 🚀 BlackBox FW-Agent — Autonomous Embedded Firmware Test Engine

**BlackBox FW-Agent** is an AI Agent for Autonomous Embedded Firmware Testing. It reads raw Arduino (`.ino`), C (`.c`), or C++ (`.cpp`) firmware source code, parses decision boundaries and pin assignments, generates deterministic and adaptive test plans, executes them on an ultra-fast C++ Software-in-the-Loop (SIL) simulator or Wokwi emulator, and maps root-cause software bugs directly to source code line numbers.

---

## 💻 Running the Web UI

You can run the web dashboard using either `make ui` or Uvicorn directly:

### Option 1: Using Makefile
```bash
make ui
```

### Option 2: Using Uvicorn Directly
```bash
python -m uvicorn server.app:app --host 0.0.0.0 --port 8000
```

Once started, open your browser and navigate to:
👉 **`http://localhost:8000/`** (Single-page static Web UI)  
👉 **`http://localhost:8000/docs`** (Interactive FastAPI Swagger Documentation)

---

## ⚡ CLI Command Line Execution

```bash
# Run test engine on a sample firmware
python -m fwagent.cli run firmware_samples/cooling_fan_buggy

# Run with optional specification file
python -m fwagent.cli run firmware_samples/door_lock_fsm/buggy --spec firmware_samples/door_lock_fsm/spec.md
```

---

## 🧪 Running Automated Unit & Integration Tests

```bash
# Run full server API test suite
$env:PYTHONPATH="src"; python -m unittest tests/test_server.py

# Run all test suites
$env:PYTHONPATH="src"; python -m unittest discover tests
```

---

## 📁 Key Deliverables & Deliverable Files

- **FastAPI Backend Server**: [server/app.py](file:///c:/Users/DR.RAJESH%20KUMAR/blackbox/server/app.py)
- **Web UI Single Page**: [static/index.html](file:///c:/Users/DR.RAJESH%20KUMAR/blackbox/static/index.html)
- **Frontend Logic & SSE Client**: [static/app.js](file:///c:/Users/DR.RAJESH%20KUMAR/blackbox/static/app.js)
- **Web UI Stylesheet**: [static/style.css](file:///c:/Users/DR.RAJESH%20KUMAR/blackbox/static/style.css)
- **API Unit & Integration Tests**: [tests/test_server.py](file:///c:/Users/DR.RAJESH%20KUMAR/blackbox/tests/test_server.py)
- **Makefile**: [Makefile](file:///c:/Users/DR.RAJESH%20KUMAR/blackbox/Makefile)
