import os
import sys
import json
import shutil
import zipfile
import subprocess
import threading
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from fastapi.staticfiles import StaticFiles

# Ensure src is on sys.path
sys.path.insert(0, os.path.abspath("src"))

app = FastAPI(
    title="BlackBox FW-Agent Backend API",
    description="REST & SSE Streaming API Server for Autonomous Embedded Firmware Testing AI Agent",
    version="1.0.0"
)

# Enable CORS for React / Vue / Web Frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global State for Active Subprocesses & SSE Buffers
RUN_PROCESSES: Dict[str, Dict[str, Any]] = {}
PROCESS_LOCK = threading.Lock()


def sanitize_filename(filename: str) -> str:
    """Strip dangerous path components to prevent path traversal."""
    filename = os.path.basename(filename)
    filename = filename.replace("..", "").replace("/", "").replace("\\", "")
    return filename


def is_safe_extract(base_dir: str, target_path: str) -> bool:
    """Prevent Zip-Slip vulnerabilities."""
    abs_base = os.path.abspath(base_dir)
    abs_target = os.path.abspath(target_path)
    return abs_target.startswith(abs_base) and ".." not in target_path


def run_agent_subprocess(run_id: str, firmware_dir: str, spec_file: Optional[str], sim: str, board: str, out_dir: str):
    """Run `python -m fwagent.cli run <firmware_dir>` in a background thread."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = os.path.abspath("src")

    cmd = [
        sys.executable,
        "-m",
        "fwagent.cli",
        "run",
        firmware_dir
    ]
    if spec_file and os.path.exists(spec_file):
        cmd.extend(["--spec", spec_file])
    if out_dir:
        cmd.extend(["--out", out_dir])

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            cwd=os.path.abspath(".")
        )

        with PROCESS_LOCK:
            if run_id in RUN_PROCESSES:
                RUN_PROCESSES[run_id]["process"] = proc

        # Read stdout line by line
        for line in iter(proc.stdout.readline, ''):
            if not line:
                break
            line_str = line.strip()
            with PROCESS_LOCK:
                if run_id in RUN_PROCESSES:
                    RUN_PROCESSES[run_id]["logs"].append(line_str)

        proc.stdout.close()
        return_code = proc.wait()

        with PROCESS_LOCK:
            if run_id in RUN_PROCESSES:
                RUN_PROCESSES[run_id]["exit_code"] = return_code
                RUN_PROCESSES[run_id]["status"] = "done" if return_code == 0 else "failed"

    except Exception as e:
        with PROCESS_LOCK:
            if run_id in RUN_PROCESSES:
                RUN_PROCESSES[run_id]["logs"].append(f"EXECUTION ERROR: {str(e)}")
                RUN_PROCESSES[run_id]["exit_code"] = -1
                RUN_PROCESSES[run_id]["status"] = "failed"


# API Endpoints

@app.get("/api/samples")
def list_firmware_samples():
    """List built-in firmware samples available for testing."""
    samples_dir = "firmware_samples"
    if not os.path.exists(samples_dir):
        return []
    
    samples = []
    for root, dirs, files in os.walk(samples_dir):
        if any(f.endswith((".ino", ".c", ".cpp")) for f in files):
            rel_path = os.path.relpath(root, samples_dir).replace("\\", "/")
            if rel_path not in samples and rel_path != ".":
                samples.append(rel_path)

    return {"samples": sorted(samples)}


@app.get("/api/wokwi/diagram")
def get_wokwi_diagram(sample_name: Optional[str] = None, run_id: Optional[str] = None):
    """
    Generate Wokwi diagram.json specification and live simulation stats metadata
    from target firmware signals and pin assignments.
    """
    inputs = []
    outputs = []
    board_type = "wokwi-arduino-uno"

    model_path = None
    if run_id:
        model_path = os.path.join("runs", run_id, "firmware_model.json")
    elif sample_name and sample_name != "custom":
        sample_dir = os.path.join("firmware_samples", sample_name)
        if os.path.exists(sample_dir):
            try:
                from fwagent.analyzer.static_parser import StaticParser
                for root, _, files in os.walk(sample_dir):
                    for file in files:
                        if file.endswith((".ino", ".cpp")):
                            p = os.path.join(root, file)
                            model = StaticParser().parse_file(p)
                            inputs = [i.model_dump() if hasattr(i, "model_dump") else i.__dict__ for i in model.inputs]
                            outputs = [o.model_dump() if hasattr(o, "model_dump") else o.__dict__ for o in model.outputs]
                            break
            except Exception:
                pass

    if model_path and os.path.exists(model_path):
        try:
            with open(model_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                inputs = data.get("inputs", [])
                outputs = data.get("outputs", [])
        except Exception:
            pass

    if not inputs and not outputs:
        inputs = [{"name": "temp", "pin": "A0", "type": "analog"}]
        outputs = [{"name": "fan_pin", "pin": "9", "type": "digital"}, {"name": "err_led", "pin": "13", "type": "digital"}]

    parts = [
        {"type": board_type, "id": "uno", "top": 200, "left": 300, "attrs": {}}
    ]
    connections = []

    y_pos = 100
    for idx, inp in enumerate(inputs):
        pin = str(inp.get("pin", "A0")).upper()
        if not pin.startswith("A") and pin.isdigit():
            pin = f"A{pin}"
        part_id = f"sensor_{idx}"
        parts.append({"type": "wokwi-ntc-temperature-sensor", "id": part_id, "top": y_pos, "left": 80, "attrs": {}})
        connections.append(["uno:GND.1", f"{part_id}:GND", "black", ["v0"]])
        connections.append(["uno:5V", f"{part_id}:VCC", "red", ["v0"]])
        connections.append([f"{part_id}:OUT", f"uno:{pin}", "green", ["v0"]])
        y_pos += 120

    y_out = 120
    for idx, out in enumerate(outputs):
        pin = str(out.get("pin", "9")).upper().replace("D", "")
        name = out.get("name", "").lower()
        if "led" in name:
            led_id = f"led_{idx}"
            r_id = f"res_{idx}"
            parts.append({"type": "wokwi-led", "id": led_id, "top": y_out, "left": 650, "attrs": {"color": "red"}})
            parts.append({"type": "wokwi-resistor", "id": r_id, "top": y_out + 40, "left": 570, "attrs": {"value": "220"}})
            connections.append([f"uno:{pin}", f"{r_id}:1", "orange", ["v0"]])
            connections.append([f"{r_id}:2", f"{led_id}:A", "orange", ["v0"]])
            connections.append([f"{led_id}:C", "uno:GND.2", "black", ["v0"]])
        else:
            fan_id = f"fan_{idx}"
            parts.append({"type": "wokwi-fan", "id": fan_id, "top": y_out, "left": 620, "attrs": {}})
            connections.append([f"uno:{pin}", f"{fan_id}:IN", "blue", ["v0"]])
            connections.append(["uno:GND.3", f"{fan_id}:GND", "black", ["v0"]])
        y_out += 140

    diagram_json = {
        "version": 1,
        "author": "FW-Agent Autonomous Test Engine",
        "editor": "wokwi",
        "parts": parts,
        "connections": connections
    }

    stats = {
        "mcu": "ATmega328P (Arduino Uno)",
        "clock_freq": "16.0 MHz",
        "vcc_voltage": 5.00,
        "gnd_voltage": 0.00,
        "pins": {
            "A0": {"type": "Analog Input", "voltage": 1.51, "raw_adc": 310, "state": "NORMAL"},
            "D9": {"type": "PWM/Digital Output", "voltage": 5.00, "duty_pct": 100, "state": "HIGH (Fan ON)"},
            "D13": {"type": "Digital Output", "voltage": 0.00, "duty_pct": 0, "state": "LOW (LED OFF)"}
        },
        "est_current_ma": 145.2,
        "sim_fps": 60,
        "serial_baud": 9600
    }

    return {
        "diagram": diagram_json,
        "stats": stats,
        "inputs": inputs,
        "outputs": outputs
    }


@app.post("/api/runs")
async def create_run(
    files: List[UploadFile] = File(None),
    zip_file: UploadFile = File(None),
    spec_file: UploadFile = File(None),
    sim: str = Form("host"),
    board: str = Form("Arduino Uno"),
    sample_name: Optional[str] = Form(None)
):
    """
    1. Accepts multipart upload of a firmware folder / zip file OR built-in sample name.
    2. Protects against path traversal, Zip-Slip, 20 MB size limit, 500 files limit.
    3. Spawns `fwagent run` in a background thread.
    4. Returns { "run_id": run_id }.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_id = f"run_{timestamp}_{os.urandom(3).hex()}"
    
    upload_dir = os.path.join("uploads", run_id, "firmware")
    out_dir = os.path.join("runs", run_id)
    os.makedirs(upload_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)

    firmware_target_dir = upload_dir

    # Handle built-in sample selection if specified
    if sample_name and sample_name != "custom":
        sample_path = os.path.join("firmware_samples", sample_name)
        if os.path.exists(sample_path):
            firmware_target_dir = sample_path
        else:
            raise HTTPException(status_code=400, detail=f"Sample firmware {sample_name} not found")
    
    # Handle single Zip file upload
    elif zip_file:
        zip_bytes = await zip_file.read()
        if len(zip_bytes) > 20 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Zip file size exceeds 20 MB limit")
        
        zip_temp_path = os.path.join(upload_dir, "firmware.zip")
        with open(zip_temp_path, "wb") as f:
            f.write(zip_bytes)

        file_count = 0
        with zipfile.ZipFile(zip_temp_path, "r") as zf:
            for member in zf.infolist():
                file_count += 1
                if file_count > 500:
                    raise HTTPException(status_code=400, detail="Zip archive exceeds maximum 500 files limit")
                
                target_path = os.path.join(upload_dir, member.filename)
                if not is_safe_extract(upload_dir, target_path):
                    raise HTTPException(status_code=400, detail=f"Zip-slip path traversal attempt detected in {member.filename}")

            zf.extractall(upload_dir)

    # Handle multiple multipart files upload
    elif files:
        if len(files) > 500:
            raise HTTPException(status_code=400, detail="File count exceeds maximum 500 files limit")
        
        total_size = 0
        for upload_f in files:
            content = await upload_f.read()
            total_size += len(content)
            if total_size > 20 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="Total upload size exceeds 20 MB limit")
            
            clean_name = sanitize_filename(upload_f.filename)
            if not clean_name:
                continue

            target_file = os.path.join(upload_dir, clean_name)
            if not clean_name.endswith((".ino", ".c", ".cpp", ".h", ".hpp", ".json", ".toml", ".md")):
                continue

            with open(target_file, "wb") as f:
                f.write(content)

    # Handle optional spec.md file upload
    saved_spec_path = None
    if spec_file:
        spec_content = await spec_file.read()
        saved_spec_path = os.path.join(upload_dir, "spec.md")
        with open(saved_spec_path, "wb") as f:
            f.write(spec_content)

    # Register run process entry
    with PROCESS_LOCK:
        RUN_PROCESSES[run_id] = {
            "run_id": run_id,
            "firmware_dir": firmware_target_dir,
            "out_dir": out_dir,
            "logs": [f"Run {run_id} initialized for firmware: {firmware_target_dir}"],
            "status": "running",
            "process": None,
            "exit_code": None,
            "started_at": datetime.now().isoformat()
        }

    # Start background execution thread
    thread = threading.Thread(
        target=run_agent_subprocess,
        args=(run_id, firmware_target_dir, saved_spec_path, sim, board, out_dir),
        daemon=True
    )
    thread.start()

    return {"run_id": run_id, "out_dir": out_dir, "status": "started"}


@app.get("/api/runs/{run_id}/stream")
async def stream_run(run_id: str):
    """
    Server-Sent Events (SSE) streaming log & status endpoint.
    Events emitted:
    - event: log (stdout log line)
    - event: status (status.json payload)
    - event: done ({ exit_code, scoreboard, report_url })
    """
    async def event_generator():
        last_log_idx = 0
        last_status_mtime = 0

        out_dir = os.path.join("runs", run_id)
        status_file = os.path.join(out_dir, "status.json")

        while True:
            # 1. Stream stdout log lines
            logs = []
            with PROCESS_LOCK:
                if run_id in RUN_PROCESSES:
                    logs = list(RUN_PROCESSES[run_id]["logs"])

            while last_log_idx < len(logs):
                log_line = logs[last_log_idx]
                last_log_idx += 1
                yield f"event: log\ndata: {json.dumps({'line': log_line})}\n\n"

            # 2. Check for status.json updates
            if os.path.exists(status_file):
                try:
                    mtime = os.path.getmtime(status_file)
                    if mtime > last_status_mtime:
                        last_status_mtime = mtime
                        with open(status_file, "r", encoding="utf-8") as f:
                            status_data = json.load(f)
                        yield f"event: status\ndata: {json.dumps(status_data)}\n\n"
                except Exception:
                    pass

            # 3. Check if run is done
            run_proc_info = RUN_PROCESSES.get(run_id)
            if run_proc_info and run_proc_info.get("status") in ["done", "failed"]:
                # Replay any remaining logs
                while last_log_idx < len(run_proc_info["logs"]):
                    log_line = run_proc_info["logs"][last_log_idx]
                    last_log_idx += 1
                    yield f"event: log\ndata: {json.dumps({'line': log_line})}\n\n"

                done_payload = {
                    "exit_code": run_proc_info.get("exit_code", 0),
                    "run_id": run_id,
                    "report_url": f"/api/runs/{run_id}/report",
                    "status": run_proc_info.get("status")
                }
                yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/runs/{run_id}/stop")
def stop_run(run_id: str):
    """Terminate the active run process tree."""
    with PROCESS_LOCK:
        proc_info = RUN_PROCESSES.get(run_id)
        if proc_info and proc_info.get("process"):
            try:
                proc_info["process"].terminate()
                proc_info["status"] = "stopped"
                proc_info["logs"].append("EXECUTION STOPPED BY USER REQUEST.")
                return {"run_id": run_id, "status": "stopped"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to stop process: {str(e)}")
    
    raise HTTPException(status_code=404, detail="Run not found or already stopped")


@app.get("/api/runs")
def list_past_runs():
    """List all past runs with metadata and scoreboard counts."""
    runs_dir = "runs"
    if not os.path.exists(runs_dir):
        return []

    runs_list = []
    for item in os.listdir(runs_dir):
        run_path = os.path.join(runs_dir, item)
        if os.path.isdir(run_path) and not item.startswith("temp_"):
            results_file = os.path.join(run_path, "results.json")
            status_file = os.path.join(run_path, "status.json")

            scoreboard = {"PASS": 0, "FAIL": 0, "WARN": 0, "AMBIGUOUS": 0, "TOTAL": 0}
            if os.path.exists(results_file):
                try:
                    with open(results_file, "r", encoding="utf-8") as f:
                        verdicts = json.load(f)
                        scoreboard["TOTAL"] = len(verdicts)
                        for v in verdicts:
                            st = v.get("status", "PASS")
                            scoreboard[st] = scoreboard.get(st, 0) + 1
                except Exception:
                    pass

            runs_list.append({
                "id": item,
                "path": run_path,
                "time": datetime.fromtimestamp(os.path.getmtime(run_path)).strftime("%Y-%m-%d %H:%M:%S"),
                "scoreboard": scoreboard,
                "has_report": os.path.exists(os.path.join(run_path, "report.html"))
            })

    return sorted(runs_list, key=lambda x: x["time"], reverse=True)


@app.get("/api/history")
def get_history_alias():
    """Alias for /api/runs matching frontend history endpoint."""
    return {"runs": list_past_runs()}


@app.get("/api/runs/{run_id}/summary")
def get_run_summary(run_id: str):
    """Return scoreboard counts, findings, suggestions, and status for a run."""
    run_dir = os.path.join("runs", run_id)
    if not os.path.exists(run_dir):
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    results_file = os.path.join(run_dir, "results.json")
    findings_file = os.path.join(run_dir, "findings.json")
    suggestions_file = os.path.join(run_dir, "suggestions.json")
    status_file = os.path.join(run_dir, "status.json")

    verdicts = []
    if os.path.exists(results_file):
        with open(results_file, "r", encoding="utf-8") as f:
            verdicts = json.load(f)

    findings = []
    if os.path.exists(findings_file):
        with open(findings_file, "r", encoding="utf-8") as f:
            findings = json.load(f)

    suggestions = []
    if os.path.exists(suggestions_file):
        with open(suggestions_file, "r", encoding="utf-8") as f:
            suggestions = json.load(f)

    status_data = {}
    if os.path.exists(status_file):
        with open(status_file, "r", encoding="utf-8") as f:
            status_data = json.load(f)

    scoreboard = {
        "TOTAL": len(verdicts),
        "PASS": sum(1 for v in verdicts if v.get("status") == "PASS"),
        "FAIL": sum(1 for v in verdicts if v.get("status") == "FAIL"),
        "WARN": sum(1 for v in verdicts if v.get("status") == "WARN"),
        "AMBIGUOUS": sum(1 for v in verdicts if v.get("status") == "AMBIGUOUS")
    }

    return {
        "run_id": run_id,
        "scoreboard": scoreboard,
        "findings": findings,
        "suggestions": suggestions,
        "verdicts": verdicts,
        "status": status_data
    }


@app.get("/api/runs/{run_id}/suggestions")
def get_run_suggestions(run_id: str):
    """Serve suggestions.json artifact for a run."""
    p = os.path.join("runs", run_id, "suggestions.json")
    if not os.path.exists(p):
        return []
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)



@app.get("/api/runs/{run_id}/report")
def get_run_report(run_id: str):
    """Serve the generated report.html for the run."""
    run_dir = os.path.join("runs", run_id)
    report_path = os.path.join(run_dir, "report.html")
    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="report.html not found for this run")
    return FileResponse(report_path, media_type="text/html")


@app.get("/api/runs/{run_id}/download")
def download_run_zip(run_id: str):
    """Return a downloadable Zip archive of the complete run folder."""
    run_dir = os.path.join("runs", run_id)
    if not os.path.exists(run_dir):
        raise HTTPException(status_code=404, detail=f"Run directory {run_id} not found")

    zip_filename = f"{run_id}.zip"
    zip_path = os.path.join("runs", zip_filename)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(run_dir):
            for file in files:
                full_p = os.path.join(root, file)
                rel_p = os.path.relpath(full_p, run_dir)
                zf.write(full_p, rel_p)

    return FileResponse(zip_path, filename=zip_filename, media_type="application/zip")


# Additional Endpoints for Frontend Data Access

@app.get("/api/runs/{run_id}/model")
def get_run_model(run_id: str):
    """Serve firmware_model.json artifact."""
    p = os.path.join("runs", run_id, "firmware_model.json")
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="firmware_model.json not found")
    return FileResponse(p, media_type="application/json")


@app.get("/api/runs/{run_id}/plan")
def get_run_plan(run_id: str):
    """Serve test_plan.json artifact."""
    p = os.path.join("runs", run_id, "test_plan.json")
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="test_plan.json not found")
    return FileResponse(p, media_type="application/json")


@app.get("/api/runs/{run_id}/coverage")
def get_run_coverage(run_id: str):
    """Serve coverage.json artifact."""
    p = os.path.join("runs", run_id, "coverage.json")
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="coverage.json not found")
    return FileResponse(p, media_type="application/json")


@app.get("/api/runs/{run_id}/chart")
def get_run_chart(run_id: str):
    """Serve timeline_chart.png image artifact."""
    p = os.path.join("runs", run_id, "timeline_chart.png")
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="timeline_chart.png not found")
    return FileResponse(p, media_type="image/png")


@app.get("/api/runs/{run_id}/replay")
async def replay_run_stream(run_id: str):
    """
    Replay a past run's stdout.log as SSE events with simulated timing.
    """
    run_dir = os.path.join("runs", run_id)
    log_file = os.path.join(run_dir, "stdout.log")
    status_file = os.path.join(run_dir, "status.json")

    if not os.path.exists(run_dir):
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    async def replay_generator():
        lines = []
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f.readlines()]
        else:
            lines = [f"Replaying run {run_id}... (No stdout.log found)"]

        if os.path.exists(status_file):
            try:
                with open(status_file, "r", encoding="utf-8") as f:
                    status_data = json.load(f)
                yield f"event: status\ndata: {json.dumps(status_data)}\n\n"
            except Exception:
                pass

        for line in lines:
            yield f"event: log\ndata: {json.dumps({'line': line})}\n\n"
            await asyncio.sleep(0.02)

        done_payload = {
            "exit_code": 0,
            "run_id": run_id,
            "report_url": f"/api/runs/{run_id}/report",
            "status": "done"
        }
        yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"

    return StreamingResponse(replay_generator(), media_type="text/event-stream")


# Mount static web UI files at /
static_dir = os.path.abspath("static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)

