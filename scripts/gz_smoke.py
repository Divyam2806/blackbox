import time
from fwagent.simulator.gazebo_adapter import GazeboSimulator

sim = GazeboSimulator(world_file="worlds/diff_drive.sdf",
                      cmd_topic="/model/vehicle_blue/cmd_vel",
                      pose_topic="/model/vehicle_blue/odometry",
                      require_gazebo=True)
sim.start()
print("mode:", sim.mode, "| world:", sim.world_name, "|", sim.backend_name)
x0 = sim._read_x()
sim._send_speed(1.0)
time.sleep(2)
x1 = sim._read_x()
print("x0 =", x0, " x1 =", x1)      # x1 > x0 means the whole gz path works
sim.stop()
