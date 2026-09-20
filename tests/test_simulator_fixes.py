"""Run with:  pytest tests/test_simulator_fixes.py -q   (uses your real fwagent.simulator.base)"""
import pytest
from fwagent.simulator.fault_layer import SharedFaultLayer
from fwagent.simulator.host_hal import HostHALSimulator
from fwagent.simulator.factory import SimulatorFactory, compare_backend_results


def fan(kind="buggy"):
    return HostHALSimulator(firmware_type=kind)


def test_glitch_is_one_shot():
    f = SharedFaultLayer()
    f.set_fault("A0", "glitch")
    assert f.apply("A0", 300) == 1023.0
    assert f.apply("A0", 300) == 300.0


def test_stuck_freezes_value_seen_before_injection():
    f = SharedFaultLayer()
    f.apply("A0", 250)
    f.set_fault("A0", "stuck")
    assert f.apply("A0", 900) == 250
    assert f.apply("A0", 100) == 250


def test_unknown_fault_raises():
    with pytest.raises(ValueError):
        SharedFaultLayer().set_fault("A0", "explode")


def test_noise_is_repeatable():
    a, b = SharedFaultLayer(seed=7), SharedFaultLayer(seed=7)
    a.set_fault("A0", "noise", delta=5); b.set_fault("A0", "noise", delta=5)
    assert [a.apply("A0", 300) for _ in range(5)] == [b.apply("A0", 300) for _ in range(5)]


def test_boundary_306_307():
    s = fan()
    s.set_input("temp", "raw:306"); s.run_for(400)
    assert s.read_pin("9") == 0
    s.set_input("temp", "raw:307"); s.run_for(400)
    assert s.read_pin("9") == 1


def test_buggy_short_turns_fan_off_when_hot():          # finding F1
    s = fan()
    s.set_input("temp", "raw:409"); s.run_for(400)
    assert s.read_pin("9") == 1
    s.inject_fault("temp", "short_to_gnd"); s.run_for(400)
    assert s.read_pin("9") == 0


def test_buggy_never_drives_error_pin():                # finding F2
    s = fan()
    s.inject_fault("temp", "open_circuit"); s.run_for(1000)
    assert s.read_pin("13") == 0


def test_good_signals_error_and_fails_safe():
    s = fan("good")
    s.set_input("temp", "raw:409"); s.run_for(400)
    s.inject_fault("temp", "short_to_gnd"); s.run_for(400)
    assert s.read_pin("13") == 1 and s.read_pin("9") == 1


def test_uart_silence_stops_serial():
    s = fan()
    s.inject_fault("uart", "silence"); s.run_for(1000)
    assert s.read_serial() == []


def test_time_remainder_is_kept():
    s = fan()
    for _ in range(4):
        s.run_for(50)
    assert s.t_ms == 200


def test_unknown_backend_raises():
    with pytest.raises(ValueError):
        SimulatorFactory.create("nonsense")


def test_gazebo_request_is_never_mislabelled(tmp_path):
    sim, notice = SimulatorFactory.create("gazebo", str(tmp_path))
    assert "gazebo" not in sim.backend_name.lower() or "plant model" in sim.backend_name.lower() \
        or notice is not None


def test_comparison_warns_when_engines_not_independent():
    class R:
        def __init__(self, t, s): self.test_id, self.status = t, s
    res = {"host": [R("T1", "PASS")], "gazebo": [R("T1", "PASS")]}
    out = compare_backend_results(res, independent={"host": True, "gazebo": False})
    assert "warning" in out
