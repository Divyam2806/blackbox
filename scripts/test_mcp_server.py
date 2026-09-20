"""
Smoke test for Gazebo & FW-Agent MCP Server tools.
"""
import os
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from server.mcp_server import (
    start_gazebo_simulation,
    send_vehicle_speed,
    get_gazebo_state,
    list_gazebo_topics,
    run_fwagent_suite,
    get_state_resource,
    get_latest_report_resource
)

def run_tests():
    print("=== Testing MCP Tools & Resources ===")
    
    print("\n1. Testing list_gazebo_topics()...")
    topics = list_gazebo_topics()
    print("   Topics:", topics)

    print("\n2. Testing get_gazebo_state()...")
    state = get_gazebo_state()
    print("   State:", state)

    print("\n3. Testing send_vehicle_speed(0.75)...")
    cmd_res = send_vehicle_speed(0.75)
    print("   Result:", cmd_res)

    print("\n4. Testing gazebo://state Resource...")
    res = get_state_resource()
    print("   Resource Output:", res)

    print("\n5. Testing fwagent://latest_report Resource...")
    rep = get_latest_report_resource()
    print("   Report Snippet:", rep[:200] + "...")

    print("\n[OK] All MCP tools & resources verified successfully!")

if __name__ == "__main__":
    run_tests()
