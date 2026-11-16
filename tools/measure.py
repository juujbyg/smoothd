#!/usr/bin/python3 -I
"""Frame pacing during a scripted touch (root, screen on, phone unlocked).

    measure.py EVENT -- touch.py ARGS...

EVENT is a tracefs event that fires once per displayed frame (for example
sde/sde_perf_crtc_update). The touch runs through /root/touch.py. Prints
the frames seen while the finger moves and shortly after, the long gaps
between them (janks), and CPU/GPU clocks sampled during the run. Tracing is
switched off and the buffer emptied afterwards.
"""
import os, re, subprocess, sys, threading, time

T = "/sys/kernel/tracing"
ev, args = sys.argv[1], sys.argv[sys.argv.index("--") + 1:]
match = os.environ.get("MATCH", "")   # only count trace lines containing this


def w(path, val):
    with open(path, "w") as f:
        f.write(val)


def r(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return "?"


samples, stop = [], threading.Event()


def sampler():
    while not stop.is_set():
        samples.append((int(r("/sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq")) // 1000,
                        int(r("/sys/devices/system/cpu/cpufreq/policy6/scaling_cur_freq")) // 1000,
                        int(r("/sys/class/kgsl/kgsl-3d0/devfreq/cur_freq")) // 1000000))
        time.sleep(0.02)


w(f"{T}/tracing_on", "0"); w(f"{T}/trace", ""); w(f"{T}/buffer_size_kb", "2048")
w(f"{T}/events/{ev}/enable", "1")
th = threading.Thread(target=sampler); th.start()
w(f"{T}/tracing_on", "1")
t0 = time.monotonic()
if args[0] == "sh":                   # any command instead of a touch
    out = subprocess.run(args[1:], capture_output=True, text=True).stdout or "cmd done"
else:
    out = subprocess.run(["python3", "-I", "/root/touch.py"] + args, capture_output=True, text=True).stdout
time.sleep(float(os.environ.get("AFTER", "0.6")))
w(f"{T}/tracing_on", "0"); stop.set(); th.join()
w(f"{T}/events/{ev}/enable", "0")
with open(f"{T}/trace") as f:
    lines = [l for l in f if not l.startswith("#")]
w(f"{T}/trace", ""); w(f"{T}/buffer_size_kb", "7")

ts = []
for l in lines:
    m = re.search(r"\s(\d+\.\d+):\s", l)
    if m and match in l:
        ts.append(float(m.group(1)))
ts.sort()
if len(ts) < 2:
    sys.exit(f"only {len(ts)} events; wrong event or screen off")
gaps = [(b - a) * 1000 for a, b in zip(ts, ts[1:])]
span = ts[-1] - ts[0]
jank = [g for g in gaps if g > 25]
print(f"touch: {out.strip().splitlines()[0] if out.strip() else '?'}")
print(f"frames {len(ts)} over {span*1000:.0f} ms = {len(ts)/span:.1f} fps")
print(f"gaps >25 ms: {len(jank)}  worst: {sorted(gaps)[-5:][::-1] and [round(g) for g in sorted(gaps)[-5:][::-1]]}")
print(f"median gap {sorted(gaps)[len(gaps)//2]:.1f} ms")
if samples:
    l, b, g = zip(*samples)
    print(f"little MHz min/avg/max {min(l)}/{sum(l)//len(l)}/{max(l)}  big {min(b)}/{sum(b)//len(b)}/{max(b)}  gpu {min(g)}/{sum(g)//len(g)}/{max(g)}")
    print("first 300 ms little/big/gpu:", [s for s in samples[:15]])
