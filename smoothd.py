#!/usr/bin/python3 -I
"""smoothd: touch boost for Ubuntu Touch on the Pixel 3a (root).

Android raises the CPU, memory bus and scheduler boost while you touch the
screen (the power HAL's INTERACTION hint), but on Ubuntu Touch nothing
sends that hint, and the kernel's cpuquiet unplugs up to 6 of the 8 cores
when the phone is calm. Every swipe and app launch then starts slow.

smoothd watches the touchscreen (read only, never grabbed) and the
backlight:

- screen on: keep all cores online (cpuquiet nr_min_cpus = all)
- finger on the screen, and BOOST_TAIL seconds after it lifts: apply the
  vendor's own INTERACTION values from /vendor/etc/powerhint.json
  (minimum clocks only; thermal-engine still caps the maximums)
- screen off: back to the values found at start

    smoothd.py [--test SECONDS] [--no-cores] [--no-boost] [--also NAME]

--also NAME also follows input devices with that name as they come and go
(tests use the virtual "gesture-pack-test-touch"). SIGUSR1 counts as a
touch, so a test can stand in for the tap that launches an app.

Stops cleanly on SIGTERM/SIGINT and restores every value it changed.
"""
import glob, json, os, select, signal, struct, sys, time

BOOST_TAIL = 1.5
EVENT = struct.Struct("llHHi")
CPUQ = "/sys/devices/system/cpu/cpuquiet/nr_min_cpus"
INTERACTION_NODES = ("CPULittleClusterMinFreq", "CPUBigClusterMinFreq", "CPUBWMinFreq",
                     "CPUBWHystTriggerCount", "CPUBWHystLength", "CPUBWHistMemory")
SCHEDTUNE = "/sys/fs/cgroup/schedtune/schedtune.boost"   # the group lomiri and apps run in
SCHEDTUNE_BOOST = "50"                                     # Android's top-app value during INTERACTION


def log(*a):
    print(time.strftime("%T"), *a, flush=True)


def read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def write(path, val):
    try:
        with open(path, "w") as f:
            f.write(val)
        return True
    except OSError:
        return False


def interaction_values():
    """{path: value} for the INTERACTION hint from the vendor's powerhint.json."""
    for p in ("/vendor/etc/powerhint.json", "/android/vendor/etc/powerhint.json"):
        try:
            with open(p) as f:
                d = json.load(f)
            break
        except (OSError, ValueError):
            d = None
    if not d:
        return {}
    paths = {n["Name"]: n["Path"] for n in d["Nodes"]}
    out = {}
    for a in d["Actions"]:
        if a["PowerHint"] == "INTERACTION" and a["Node"] in INTERACTION_NODES:
            out[paths[a["Node"]]] = a["Value"]
    return out


def touch_device():
    best = None
    for dev in glob.glob("/sys/class/input/event*/device/name"):
        name = read(dev) or ""
        ev = "/dev/input/" + dev.split("/")[4]
        if name == "synaptics_dsx":
            return ev, name
        caps = read(os.path.dirname(dev) + "/capabilities/abs") or "0"
        if int(caps.split()[-1], 16) & (1 << 0x35) and best is None:   # ABS_MT_POSITION_X
            best = (ev, name)
    return best


def backlight_on():
    for b in glob.glob("/sys/class/backlight/*/brightness"):
        v = read(b)
        if v and v != "0":
            return True
    return False


class Knobs:
    """Remembers the stock value of everything it writes, to put it back."""

    def __init__(self):
        self.stock = {}

    def set(self, path, val):
        if path not in self.stock:
            cur = read(path)
            if cur is None:
                return
            self.stock[path] = cur
        write(path, val)

    def reset(self, paths):
        for p in paths:
            if p in self.stock:
                v = self.stock[p]
                if not write(p, v) and p == CPUQ:
                    write(p, "1")          # cpuquiet refuses 0 once raised; 1 behaves the same

    def reset_all(self):
        self.reset(list(self.stock))


def main():
    args = sys.argv[1:]
    test = float(args[args.index("--test") + 1]) if "--test" in args else None
    use_cores, use_boost = "--no-cores" not in args, "--no-boost" not in args
    dev = touch_device()
    if not dev:
        sys.exit("no touchscreen found")
    boost = interaction_values() if use_boost else {}
    if use_boost and os.path.exists(SCHEDTUNE):
        boost[SCHEDTUNE] = SCHEDTUNE_BOOST
    ncpu = str(len(glob.glob("/sys/devices/system/cpu/cpu[0-9]*")))
    log(f"touch {dev[0]} ({dev[1]}); cores={'on' if use_cores else 'off'}; boost {len(boost)} values")
    k = Knobs()
    stop = []
    signal.signal(signal.SIGTERM, lambda *_: stop.append(1))
    signal.signal(signal.SIGINT, lambda *_: stop.append(1))
    fds = [os.open(dev[0], os.O_RDONLY | os.O_NONBLOCK)]
    also = args[args.index("--also") + 1] if "--also" in args else None
    extra = {}                                   # event path -> fd, for --also devices
    kicked = []
    signal.signal(signal.SIGUSR1, lambda *_: kicked.append(1))
    wake_r, wake_w = os.pipe()                   # signals wake select() at once
    os.set_blocking(wake_r, False); os.set_blocking(wake_w, False)
    signal.set_wakeup_fd(wake_w)
    fds.append(wake_r)
    screen, boosted, last_touch, next_screen_check = None, False, 0.0, 0.0
    start = time.monotonic()
    try:
        while not stop and (test is None or time.monotonic() - start < test):
            now = time.monotonic()
            if now >= next_screen_check:
                on = backlight_on()
                if on != screen:
                    screen = on
                    if on and use_cores:
                        k.set(CPUQ, ncpu)
                    elif not on:
                        k.reset_all()
                        boosted = False
                    log("screen", "on" if on else "off")
                if also:
                    for n in glob.glob("/sys/class/input/event*/device/name"):
                        ev = "/dev/input/" + n.split("/")[4]
                        if read(n) == also and ev not in extra:
                            try:
                                extra[ev] = os.open(ev, os.O_RDONLY | os.O_NONBLOCK)
                            except OSError:
                                pass
                next_screen_check = now + 0.5
            timeout = 0.5
            if boosted:
                timeout = max(0.0, min(timeout, last_touch + BOOST_TAIL - now))
            try:
                r, _, _ = select.select(fds + list(extra.values()), [], [], timeout)
            except InterruptedError:
                r = []
            now = time.monotonic()
            data = b""
            for f in r:
                if f == wake_r:
                    try:
                        os.read(wake_r, 64)
                    except BlockingIOError:
                        pass
                    continue
                try:
                    data += os.read(f, EVENT.size * 64)
                except BlockingIOError:
                    pass
                except OSError:                  # a virtual device went away
                    for ev, ef in list(extra.items()):
                        if ef == f:
                            os.close(ef)
                            del extra[ev]
            if kicked:
                kicked.clear()
                data = b"kick"
            if data:
                last_touch = now
                if not boosted and boost and screen is not False:
                    if use_cores:
                        k.set(CPUQ, ncpu)              # cores first: an offline core has no cpufreq files
                    for p, v in boost.items():
                        k.set(p, v)
                    boosted = True
            if boosted and now - last_touch >= BOOST_TAIL:
                k.reset(list(boost))
                boosted = False
    finally:
        k.reset_all()
        log("stopped, values restored")


if __name__ == "__main__":
    main()
