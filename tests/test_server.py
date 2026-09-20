import os
import sys
import unittest
import zipfile
import tempfile
from fastapi.testclient import TestClient

# Ensure src is on sys.path
sys.path.insert(0, os.path.abspath("src"))

from server.app import app


class TestServerAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_samples_endpoint(self):
        response = self.client.get("/api/samples")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("samples", data)

    def test_upload_validation_and_zip_slip_rejection(self):
        # Create a malicious zip file containing path traversal
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_zip:
            zip_path = tmp_zip.name

        try:
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("../../etc/passwd", "root:x:0:0")

            with open(zip_path, "rb") as f:
                response = self.client.post(
                    "/api/runs",
                    files={"zip_file": ("malicious.zip", f, "application/zip")}
                )

            self.assertEqual(response.status_code, 400)
            self.assertIn("Zip-slip path traversal attempt detected", response.json()["detail"])
        finally:
            if os.path.exists(zip_path):
                os.remove(zip_path)

    def test_run_cooling_fan_buggy_and_report(self):
        # Trigger run for cooling_fan_buggy built-in sample
        response = self.client.post(
            "/api/runs",
            data={"sample_name": "cooling_fan_buggy", "sim": "host", "board": "Arduino Uno"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("run_id", data)
        run_id = data["run_id"]

        # Stream SSE log events
        stream_resp = self.client.get(f"/api/runs/{run_id}/stream")
        self.assertEqual(stream_resp.status_code, 200)
        stream_content = stream_resp.text

        # Verify streaming content contains at least one PASS and one FAIL line
        self.assertIn("PASS", stream_content)
        self.assertIn("FAIL", stream_content)

        # Verify report endpoint returns HTTP 200 after completion
        report_resp = self.client.get(f"/api/runs/{run_id}/report")
        self.assertEqual(report_resp.status_code, 200)
        self.assertIn("<!DOCTYPE html>", report_resp.text)


if __name__ == "__main__":
    unittest.main()
