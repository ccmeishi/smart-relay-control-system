"""先发 Ctrl+C 进 REPL, 然后 upload boot.py + main.py + reset"""
import serial, time, subprocess, sys

SERIAL = "COM5"
BAUD = 115200

print("1. 发 Ctrl+C 进 REPL...")
s = serial.Serial(SERIAL, BAUD, timeout=2)
time.sleep(0.5)
s.write(b"\x03")
time.sleep(0.5)
s.write(b"\x03")
time.sleep(0.5)
data = s.read(300).decode(errors="replace")
print("   REPL got:", data[:150])
s.close()

print("\n2. 等 2s 让串口完全释放...")
time.sleep(2)

print("\n3. upload 文件 (mpremote connect COM5 cp FILE :FILE)...")
files = ["boot.py", "main.py", "modbus_gw.py"]
for name in files:
    src = f"E:\\shixiproject\\traeproject1\\simulator\\esp32\\{name}"
    dst = ":" + name
    cmd = f'python -m mpremote connect {SERIAL} cp "{src}" "{dst}"'
    print(f"   $ {cmd}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=25)
    out = (r.stdout + r.stderr).strip()[:100]
    print(f"   -> {out}" if out else f"   -> ok (empty output)")

print("\n4. reset 板子...")
cmd2 = f"python -m mpremote connect {SERIAL} reset"
r = subprocess.run(cmd2, shell=True, capture_output=True, text=True, timeout=15)
print("reset done")
