# smoothd: a touch boost for Ubuntu Touch on the Pixel 3a

On the Pixel 3a (sargo/bonito) Ubuntu Touch feels slower than it should:
apps take long to open, and swipes and the app drawer stutter at the start.
smoothd fixes most of it. On my Pixel 3a XL, System Settings opens in about
1.4 s instead of 2.0 s.

## Why it's slow

1. **The kernel unplugs 6 of the 8 cores.** The UBports kernel runs CPUQuiet
   with the `rqbalance` governor from boot. With the screen on and the phone
   calm, only `cpu0-1` (two little cores) are online. The others come back
   one at a time, 127 ms apart, once the run queue is already long, so every
   app launch and the start of every swipe run on two little cores. Android
   keeps all eight online.
2. **There's no touch boost.** Android raises the minimum CPU clocks, the
   memory bus and the scheduler boost while you touch the screen (the power
   HAL's `INTERACTION` hint, defined in `/vendor/etc/powerhint.json`).
   Nothing on Ubuntu Touch sends that hint.

## What smoothd does

smoothd is a small root service (Python standard library only). It reads
the touchscreen (it never grabs it, so apps still get every touch) and the
backlight:

- **Screen on:** all cores stay online.
- **While you touch, and for 1.5 s after:** it applies the vendor's own
  `INTERACTION` values from `powerhint.json`. These are minimum clocks only:
  thermal limits still apply.
- **Screen off:** everything goes back to the values it found.

It stops cleanly and puts every value back.

## Measured (System Settings launch, 3 runs each)

Frame timing comes from the display driver's retire fence, one marker per
frame shown (`tools/measure.py`).

| | Total launch | Longest freeze |
|---|---|---|
| Stock | 1.9–2.1 s | 1.07–1.35 s |
| All cores online | 1.5–1.7 s | 0.90–0.94 s |
| smoothd (cores + touch boost) | 1.34–1.49 s | 0.67–0.80 s |

Battery with the screen on and idle: 167–176 mA stock, 174–183 mA with
smoothd, which is within noise. With the screen off it costs nothing,
because the stock values are back.

## Install

Tested on a Pixel 3a XL with Ubuntu Touch 24.04-2.x (build 283). It only
writes settings that exist on the phone, but it's untested on other devices.

Copy this folder to the phone, then as root:

```sh
bash install.sh          # installs and starts it; survives reboots and OTA updates
bash /root/smoothd/install.sh remove    # stops it, restores stock, removes it
```

It writes only `/root/smoothd/` and `/etc/systemd/system/smoothd.service`
on the writable partition. The read-only system image isn't touched.

To try it without installing: `python3 -I smoothd.py --test 60` (runs for
60 s, then restores stock).

## Tests

```sh
python3 -I -m unittest discover -s tests
```

`tools/measure.py` measures frame pacing during a scripted touch (it uses
`touch.py` from [lomiri-gestures](https://github.com/juujbyg/lomiri-gestures)
for the virtual touchscreen).

## The real fix

This is a workaround. The real fix belongs in the device port: turn off
cpuquiet while the display is on, and send the power HAL's `INTERACTION`
hint on touch. Reported to the Pixel 3a port:
[cpuquiet and the missing touch boost](https://gitlab.com/ubports/porting/reference-device-ports/android9/google-pixel-3a/google-sargo/-/work_items/2).
While measuring I also found a screen-off battery drain:
[the phone resumes every ~4.5 s](https://gitlab.com/ubports/porting/reference-device-ports/android9/google-pixel-3a/google-sargo/-/work_items/3).

## License

GPL-3.0-or-later
