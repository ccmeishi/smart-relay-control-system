"""Modbus TCP 从站模拟器 pytest 套件

覆盖目标文件：simulator/tools/modbus_slave_sim.py

测试策略：
- 用 pytest fixture 启动一个真实的从站进程（ThreadingTCPServer，绑定到 127.0.0.1 随机端口）
- 用 pymodbus 客户端做集成测试
- 不用 mock，目标是黑盒验证真实行为

运行：
    pip install -r ../requirements-dev.txt
    pytest test_modbus_slave_sim.py -v
"""
