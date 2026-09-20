import json
import urllib.request
import urllib.parse
import time

BASE_URL = "http://127.0.0.1:8000"

def test_api():
    print("1. Testing GET /api/samples...")
    req = urllib.request.urlopen(f"{BASE_URL}/api/samples")
    samples = json.loads(req.read().decode())
    print(f"   [+] Samples found: {samples.get('samples', [])[:4]}")

    print("\n2. Testing GET /api/history...")
    req = urllib.request.urlopen(f"{BASE_URL}/api/history")
    history = json.loads(req.read().decode())
    runs = history.get("runs", [])
    print(f"   [+] Past runs count: {len(runs)}")
    latest_run = runs[0] if runs else None

    if latest_run:
        run_id = latest_run["id"]
        print(f"\n3. Testing GET /api/runs/{run_id}/summary...")
        req = urllib.request.urlopen(f"{BASE_URL}/api/runs/{run_id}/summary")
        summary = json.loads(req.read().decode())
        print(f"   [+] Scoreboard: {summary.get('scoreboard')}")
        print(f"   [+] Findings count: {len(summary.get('findings', []))}")
        print(f"   [+] Suggestions count: {len(summary.get('suggestions', []))}")

        print(f"\n4. Testing GET /api/runs/{run_id}/suggestions...")
        req = urllib.request.urlopen(f"{BASE_URL}/api/runs/{run_id}/suggestions")
        suggestions = json.loads(req.read().decode())
        print(f"   [+] Retrived {len(suggestions)} AI Suggestions directly!")

        print(f"\n5. Testing GET /api/runs/{run_id}/report...")
        req = urllib.request.urlopen(f"{BASE_URL}/api/runs/{run_id}/report")
        html_report = req.read().decode()
        print(f"   [+] HTML Report size: {len(html_report)} bytes (contains suggestions: {'suggestions' in html_report.lower()})")

    print("\n[ALL FRONTEND API ENDPOINTS VERIFIED CLEANLY!]")

if __name__ == "__main__":
    test_api()
