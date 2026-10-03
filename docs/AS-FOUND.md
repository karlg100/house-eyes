# As found: the live Pi on 2026-10-03

A read-only survey of `eyes.local` over SSH. Nothing on the Pi was changed
apart from one SSH public key added to `~karlg/.ssh/authorized_keys` to allow
the survey (the line ending `claude-cowork-house-eyes`; safe to delete).

The config files referred to below are copied verbatim in
[`config/as-found/`](../config/as-found/).

## System

| | |
|---|---|
| Board | Raspberry Pi 4 Model B Rev 1.5 |
| OS | Raspbian GNU/Linux 11 (bullseye), 32-bit userland (`armhf`) |
| Image | Raspberry Pi reference 2023-05-03, pi-gen stage4 (Desktop) |
| Kernel | `6.1.21-v8+` (64-bit kernel, the Pi 4 default) |
| Hostname | `eyes`, advertised as `eyes.local` by avahi |
| User | `karlg`, passwordless sudo |
| Disk | 29 GB root, 4.4 GB used |
| Time zone | America/New_York |
| Network | Wifi via `wpa_supplicant` + `dhcpcd`. Two saved networks: `SCN-IoT`, `TheInternet`. Had 192.168.1.94 |
| Default target | `multi-user.target` (console). `lightdm` is enabled but never starts |

## Display

- `tvservice -s`: `DVI CUSTOM RGB full 4:3, 640x480 @ 60.00Hz, progressive`
- `/boot/config.txt`: `hdmi_group=2`, `hdmi_mode=87`,
  `hdmi_cvt=640 480 60 1 0 0 0`, `dtoverlay=vc4-fkms-v3d`
  (`vc4-kms-v3d` commented out), `max_framebuffers=1`, `disable_overscan=1`,
  `gpu_mem=128`. `hdmi_force_hotplug` is commented out.
- `/etc/X11/xorg.conf`: a single `ServerFlags` section turning off blanking
  and DPMS. X picks the `modesetting` driver by itself.

## Startup

`/etc/rc.local`, run by systemd's `rc-local.service` as root:

```sh
#cd /boot/Pi_Eyes;xinit /usr/bin/python3 cyclops-dual.py :0 &
#cd /boot/Pi_Eyes;xinit /usr/bin/python3 cyclops.py :0 &
cd /boot/Pi_Eyes;xinit /usr/bin/python3 tri-eyes.py :0 &
exit 0
```

Running processes after boot: `xinit` → `/usr/lib/xorg/Xorg :0` and
`/usr/bin/python3 tri-eyes.py :0`, all as root. `tri-eyes.py` used about 28%
of one core.

## Software

Python 3.9. Packages that matter:

| Package | Version | Installed by |
|---|---|---|
| pi3d | 2.49 | pip, `/usr/local/lib/python3.9/dist-packages` |
| svg.path | 6.3 | pip |
| Adafruit-Blinka | 8.20.0 | pip |
| adafruit-circuitpython-ads1x15 | 2.2.22 | pip |
| numpy | 1.19.5 | apt (`python3-numpy`) |
| Pillow | 8.1.2 | apt (`python3-pil`) |
| RPi.GPIO | 0.7.0 | apt (`python3-rpi.gpio`) |
| xinit | 1.4.0 | apt |
| xserver-xorg-core | 1.20.11 | apt |

## Code on the Pi

Two copies exist:

- **`/boot/Pi_Eyes/`** is what runs. It was put there by Adafruit's installer
  (a zip of `adafruit/Pi_Eyes` master) and edited in place as root. It is not
  a git checkout.
- **`~karlg/Pi_Eyes/`** is a clone of `git@github.com:karlg100/Pi_Eyes.git`,
  clean and in sync with `origin/master` at `956c7f1`. Nothing runs from here.

Comparing the two:

| File | Status |
|---|---|
| `tri-eyes.py` | Identical in both, and identical on GitHub |
| `cyclops.py`, `gfxutil.py`, `snake_eyes_bonnet.py`, `graphics/` | Identical, unmodified upstream |
| `eyes.py` | `/boot` copy has `CRAZY_EYES = True`; the git copy has upstream's `False`. This repo carries the upstream one |
| `cyclops-dual.py`, `eyes-champney.py` | Only in `/boot`. Never committed. Now in `eyes/variants/` |
| `Pi_Eyes-master/` | Only in `/boot`. A stray second copy of upstream from re-running the installer. Not carried over |
| `fbx2`, `fbx2.c`, `Makefile` | Upstream's SPI-display mirror tool. Not used with HDMI. Not carried over |

## How it was originally built

Reconstructed from `~karlg/.bash_history`:

1. Flashed the 2023-05-03 bullseye Desktop image.
2. `git clone https://github.com/adafruit/Raspberry-Pi-Installer-Scripts.git`
   (at commit `339cccf`) and `sudo bash pi-eyes.sh`, choosing Pi 4 and an HDMI
   screen, with USB ethernet gadget support. Run more than once.
3. Hand edits to `/boot/config.txt` and `/etc/rc.local`, and
   `sudo systemctl set-default multi-user.target`.
4. Experiments in `/boot/Pi_Eyes`: `cyclops-dual.py`, then `eyes-champney.py`,
   then `eyes-champney-beta.py`, which became `tri-eyes.py`.
5. 2023-10-29: forked Pi_Eyes on GitHub, committed `tri-eyes.py` as "added
   triple eyed version", and pointed `rc.local` at it.

## What tri-eyes.py changes

Compared with upstream `eyes.py`:

- All eyes use `graphics/cyclops-eye.svg` for their shape, and the dragon iris
  and sclera textures.
- A third set of geometry (`centerEye`, `centerIris`, `centerUpperEyelid`,
  `centerLowerEyelid`) placed at `eyePositionC = 0`.
- Left and right eyes pushed outward: `eyePosition = (DISPLAY.width / 4) + 90`.
- The centre eye gets its own motion, blink and eyelid-tracking state
  (`curXC`/`curYC`, `blinkStateCenter`, `trackingPosC`). Its independent motion
  is only used when `CRAZY_EYES` is `True`; otherwise it follows the others.

## On the Pi but not part of the eyes

Left alone, and not reproduced by `install.sh`:

- USB ethernet gadget mode: `dtoverlay=dwc2` in `config.txt` and
  `modules-load=dwc2,g_ether` in `cmdline.txt`.
- An OpenCV people-counting experiment from July 2023:
  `~/human-counting-project-code.py`, a 16 MB `.mp4`, and `opencv-python`,
  `imutils` and build dependencies.
- The desktop image's extras: CUPS, Bluetooth, ModemManager, lightdm and so on.
- Root crontab entries for 08:00 and 17:00 whose `vcgencmd display_power`
  commands are commented out.
- `~/Raspberry-Pi-Installer-Scripts/`, the Adafruit installer checkout.
