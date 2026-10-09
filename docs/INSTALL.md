# Install from scratch

Rebuilds the eyes Pi on a blank SD card. About 20 minutes, most of it waiting.

## You need

- Raspberry Pi 4 Model B (the original is a Rev 1.5)
- microSD card, 8 GB or more (the original is 32 GB)
- Projector on the Pi's HDMI port. Use **HDMI0**, the micro-HDMI socket next to
  the USB-C power socket.
- Wifi details for the network the Pi will live on

## 1. Flash the SD card

Use Raspberry Pi Imager and pick **Raspberry Pi OS (Legacy, 32-bit) with
desktop**, the **bullseye** release. The original was built from
`2023-05-03-raspios-bullseye-armhf.img.xz`:

<https://downloads.raspberrypi.com/raspios_armhf/images/raspios_armhf-2023-05-03/>

Two things matter here:

- **Desktop, not Lite.** On a Pi 4 the eyes draw through X, so Xorg has to be
  installed.
- **Bullseye, not bookworm or later.** Newer releases move `/boot` to
  `/boot/firmware`, refuse system-wide `pip3 install`, and drop the
  `vc4-fkms-v3d` driver setup this relies on. `install.sh` has only been run on
  bullseye.

In Imager's settings (the gear icon) set:

| Setting | Value |
|---|---|
| Hostname | `eyes` |
| Enable SSH | yes |
| Username | `karlg` |
| Wifi SSID and password | your network |
| Wifi country | `US` |
| Time zone | `America/New_York` |

## 2. First boot

Put the card in, power on, wait a couple of minutes, then:

```sh
ssh karlg@eyes.local
```

The desktop will be showing on the projector at this point. That's expected.

## 3. Run the installer

```sh
sudo apt-get install -y git        # already present on the desktop image
git clone <this repo's URL> house-eyes
cd house-eyes
sudo ./install.sh
sudo reboot
```

If the repo isn't on GitHub yet, copy it over instead:
`scp -r house-eyes karlg@eyes.local:` from the machine that has it.

After the reboot the projector should show a few lines of boot text and then
the three eyes, roughly 15 to 20 seconds after power-on.

## 4. Optional: people tracking

```sh
sudo ./tracker/install-tracker.sh
sudo reboot
```

See [TRACKING.md](TRACKING.md) for what it installs and how to calibrate.

## What install.sh does

It is a non-interactive version of Adafruit's `pi-eyes.sh` (answers: Pi 4,
HDMI screen, no GPIO-halt, no ADC) plus the changes made by hand afterwards.

1. **Packages.** `apt-get install python3-pip python3-dev python3-pil
   python3-numpy python3-smbus python3-rpi.gpio libatlas-base-dev xinit`, then
   `pip3 install pi3d==2.49 svg.path==6.3 Adafruit-Blinka==8.20.0
   adafruit-circuitpython-ads1x15==2.2.22`. The pinned versions are the ones on
   the original Pi. The Adafruit libraries are only there because
   `tri-eyes.py` imports `snake_eyes_bonnet.py`; no bonnet is fitted.
2. **Code.** Copies `eyes/` to `/boot/Pi_Eyes/`.
3. **Boot target.** `systemctl set-default multi-user.target` so the desktop
   doesn't start, and removes console autologin.
4. **`/boot/config.txt`** (original saved as `config.txt.house-eyes.orig`):

   | Line | Why |
   |---|---|
   | `dtoverlay=vc4-fkms-v3d` (replaces `vc4-kms-v3d`) | pi3d needs the "fake KMS" driver |
   | `max_framebuffers=1` | single display |
   | `disable_overscan=1` | use the whole frame |
   | `gpu_mem=128` | memory for the GPU |
   | `hdmi_group=2`, `hdmi_mode=4` | standard 640x480 @ 60 Hz boot mode (any `hdmi_cvt` line is commented out) |
   | `hdmi_force_hotplug=1` | output HDMI even if the projector is off at boot |

5. **`/etc/X11/xorg.conf`.** Disables screen blanking and DPMS.
6. **`/etc/rc.local`.** Adds
   `cd /boot/Pi_Eyes;xinit /usr/bin/python3 tri-eyes.py :0 &` before `exit 0`.

It is safe to run again. To boot a different eye program:
`sudo EYES=cyclops.py ./install.sh`.

## Differences from the original Pi

The original was configured by hand over several evenings. `install.sh`
reproduces what makes the eyes work and leaves out what doesn't. See
[AS-FOUND.md](AS-FOUND.md) for the full list. The ones worth knowing:

- The original also has USB ethernet gadget mode enabled (`dtoverlay=dwc2`,
  `modules-load=dwc2,g_ether`). It has no effect on the display and is not
  applied.
- The original used a custom 640x480 mode (`hdmi_mode=87` + `hdmi_cvt`) and
  left `hdmi_force_hotplug` off. On 2026-10-08 that mode gave "no signal" on
  the Hichip projector (scan rate too low), so both were changed on the Pi and
  in `install.sh`. The pre-change file is `/boot/config.txt.bak-2026-10-08`.
- Wifi, hostname, user, locale and time zone come from Raspberry Pi Imager,
  not from `install.sh`.
