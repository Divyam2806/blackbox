"""
Unit tests for Simulator Adapters, Shared Fault Layer, and Simulator Factory.
"""
import pytest
from fwagent.simulator.base import Simulator, Obs
from fwagent.simulator.fault_layer import SharedFaultLayer
from fwagent.simulator.host_hal import HostHALSimulator
from fwagent.simulator.gazebo_adapter import GazeboSimulator
from fwagent.simulator.renode_adapter import RenodeSimulator
from fwagent.simulator.wokwi_adapter import WokwiAdapter
from fwagent.simulator.factory import SimulatorFactory, compare_backend_results


def test_shared_fault_layer():
    fl = SharedFaultLayer(rail_low=0.0, rail_high=1023.0)

    # Normal value without fault
    assert fl.transform("temp", 306.0) == 306.0

    # Open circuit fault
    fl.set_fault("temp", "open_circuit")
    assert fl.transform("temp", 306.0) == 1023.0

    # Short to GND fault
    fl.set_fault("temp", "short_to_gnd")
    assert fl.transform("temp", 306.0) == 0.0

    # Stuck fault
    fl.clear_fault("temp")
    fl.transform("temp", 250.0)  # Record 250
    fl.set_fault("temp", "stuck")
    assert fl.transform("temp", 350.0) == 250.0

    # Clear faults
    fl.clear_all()
    assert fl.transform("temp", 400.0) == 400.0


def test_simulator_factory_auto():
    sim, fallback = SimulatorFactory.create("auto", "firmware_samples/cooling_fan_buggy")
    assert sim is not None
    assert hasattr(sim, "reset")
    assert hasattr(sim, "run_for")


def test_gazebo_adapter_conformance():
    sim = GazeboSimulator()
    avail, reason = sim.available()
    assert isinstance(avail, bool)

    sim.reset()
    sim.set_input("temp", 35.0)
    sim.run_for(100)
    p_obs = sim.read_physical_observations()
    assert isinstance(p_obs, list)


def test_backend_comparison_matrix():
    from fwagent.models import Verdict
    v1 = Verdict(test_id="T01", status="PASS", expected="A", observed="A")
    v2 = Verdict(test_id="T01", status="PASS", expected="A", observed="A")
    v3 = Verdict(test_id="T02", status="FAIL", expected="A", observed="B")
    v4 = Verdict(test_id="T02", status="FAIL", expected="A", observed="B")

    results = {
        "host": [v1, v3],
        "wokwi": [v2, v4],
    }

    comp = compare_backend_results(results)
    assert comp["agreement_rate"] == 100.0
    assert comp["total_tests"] == 2
    assert len(comp["matrix"]) == 2
