# VM test of the install procedure

Run on 2026-10-03 to check that [INSTALL.md](INSTALL.md) and `install.sh`
are complete.

## Setup

- QEMU 8.2 emulating a Raspberry Pi 3B (`-M raspi3b`). This QEMU version has
  no Pi 4 machine.
- The stock `2023-05-03-raspios-bullseye-armhf.img`, the same image the real
  Pi was built from, booted with its own `kernel8.img` (kernel `6.1.21-v8+`,
  same as the real Pi).
- User `karlg` and SSH enabled through `userconf.txt` and `ssh` in the boot
  partition, which is what Raspberry Pi Imager does.

## What was done

1. Booted the untouched image. It came up in the desktop
   (`graphical.target`).
2. Copied the repo in and ran `sudo ./install.sh`. It finished without errors.
3. Powered off and cold-booted.

## Results

| Check | Result |
|---|---|
| `install.sh` runs to completion on a stock image | Pass |
| apt and pip packages install at the pinned versions | Pass |
| `/boot/Pi_Eyes/` populated | Pass |
| `systemctl get-default` is `multi-user.target` | Pass |
| `/boot/config.txt` has the same display settings as the real Pi | Pass |
| `/etc/rc.local` has the `xinit ... tri-eyes.py :0` line | Pass |
| Running `install.sh` twice leaves `config.txt` unchanged the second time | Pass (checked on the stock `config.txt` outside the VM) |
| On reboot, `rc.local` starts `xinit`, X comes up and `tri-eyes.py` launches with no login | Pass |
| `tri-eyes.py` draws three eyes | Pass, with the two emulator workarounds below |

## Emulator limits

The emulated board is not a real Pi, so two things had to be worked around to
get as far as a picture. Neither applies to real hardware.

1. `RPi.GPIO` refuses to load ("This module can only be run on a Raspberry
   Pi!") and Adafruit's `board` module doesn't recognise the machine. For the
   rendering check, `tri-eyes.py` was started by hand with stub `RPi.GPIO`,
   `board` and `busio` modules on `PYTHONPATH`. On the unmodified boot, the
   chain ran exactly as documented up to this import and stopped there.
2. QEMU has no VideoCore GPU, so the `vc4` kernel module doesn't load by
   itself. pi3d looks for `vc4` in `lsmod` to decide whether to draw through
   X. `sudo modprobe vc4` was run by hand, after which pi3d rendered through
   X with Mesa's software renderer.

Not covered by this test:

- The HDMI mode. QEMU ignores `config.txt`, so the screenshot is 800x480,
  not 640x480, and the eyes are spaced accordingly.
- Real GPU rendering and frame rate.
- Wifi.
- Colours in the screenshot may not match the projector.

In the test sandbox apt was pointed at an HTTPS mirror through a proxy. That
is a property of the sandbox and not part of the procedure.
