# Operations

## Stop, start, restart

```sh
# Stop
sudo killall xinit

# Start (what /etc/rc.local runs at boot)
cd /boot/Pi_Eyes && sudo xinit /usr/bin/python3 tri-eyes.py :0 &

# Restart everything
sudo reboot
```

Run the start command in the foreground (drop the `&`) when testing a change:
Python errors print straight to your terminal, and Ctrl-C stops it.

## Blank the projector without stopping the eyes

```sh
vcgencmd display_power 0     # HDMI off
vcgencmd display_power 1     # HDMI on
```

Root's crontab on the original Pi has two entries for doing this on a
schedule (off at 08:00, on at 17:00). Both commands are commented out, so
they currently do nothing. To enable, `sudo crontab -e` and remove the `#`
before each `vcgencmd`.

## Changing the code

The running copy is `/boot/Pi_Eyes/`, owned by root. To deploy a change from
this repo:

```sh
cd ~/house-eyes && git pull
sudo ./install.sh        # re-copies eyes/ and re-applies settings
sudo reboot              # or stop and start as above
```

For a quick experiment, edit `/boot/Pi_Eyes/tri-eyes.py` in place with
`sudo vi`, restart, and copy the result back into the repo when it's right.

## Tuning the picture

All in `eyes/tri-eyes.py`:

| What | Where | Current value |
|---|---|---|
| Eye size (radius in pixels) | `eyeRadius`, or `--radius N` on the command line | `128` |
| Left/right eye distance from centre | `EYE_SPACING` (fraction of screen width), or `--spacing 0.26` on the command line | `0.265`, about 509 px at 1920 wide (was width/4 + 90 = 570 px; moved in about 11% on 2026-10-11 to line up with the windows) |
| Centre eye offset | `eyePositionC` | `0` |
| Each eye wanders independently | `CRAZY_EYES` | `False` (all three move together) |
| Automatic blinking | `AUTOBLINK` | `True` |
| Rogue eyes: while wandering with nobody to watch, one eye (sometimes two) looks somewhere else, then drifts back into sync | `ROGUE`, `ROGUE_EVERY`, `ROGUE_TWO`, `ROGUE_LONG`, `ROGUE_GLANCE`, `ROGUE_LINGER`, `ROGUE_RETARGET` | On; an episode every 8 to 30 s; 30% of the time two eyes; 35% of the time it lingers 3 to 6 s, otherwise a 0.6 to 1.5 s glance |
| Eye shape | `parse("graphics/cyclops-eye.svg")` | cyclops shape for all three |
| Iris and sclera textures | `irisMap`, `scleraMap` | `dragon-iris.jpg`, `dragon-sclera.png` |

`--radius` goes before the display number:
`sudo xinit /usr/bin/python3 tri-eyes.py --radius 150 :0`. To make it
permanent, put it in the `/etc/rc.local` line.

Rogue eyes can be turned off with `--no-rogue`, or made frequent for testing
with `--rogue-every 2 4` (seconds between episodes), on the same command line.
They only happen while the eyes wander on their own; the moment the people
tracker has someone to watch, all eyes go back under its control.

To try a spacing without editing the file, stop the eyes and start them by
hand with `--spacing`, e.g. `cd /boot/Pi_Eyes && sudo xinit /usr/bin/python3
tri-eyes.py --spacing 0.26 :0`, then put the value you like into `EYE_SPACING`.

The Pi boots at 640x480 (`hdmi_mode=4` in `/boot/config.txt`), but X then
picks the projector's preferred mode, currently 1920x1080. The eye program
draws at whatever X is running, and the eye positions scale with the width.
Check with `sudo DISPLAY=:0 xrandr`.

## Gaze input

`tri-eyes.py` listens on UDP port 5005 for gaze targets, in screen
coordinates from -1 to 1 (x -1 = screen left, y -1 = down):

- `x y`: all three eyes look at one point.
- `xl yl xc yc xr yr`: one point per eye (screen-left, centre, screen-right).
- Either form can end with `p=0.9` to set the pupil size (0 small to 1 wide).

While messages arrive the eyes ease toward their points; 2 seconds after the
last one they wander again. The people tracker uses this (see
[TRACKING.md](TRACKING.md)); you can too: `echo "1 0" | nc -u -w0 eyes.local 5005`.
Start `tri-eyes.py` with `--gaze-port 0` to turn it off.

## Other eye programs

| File | What it shows |
|---|---|
| `tri-eyes.py` | Three eyes (the house) |
| `eyes.py` | Adafruit's two eyes |
| `cyclops.py` | Adafruit's single large eye |
| `variants/cyclops-dual.py` | `cyclops.py` at half size, with the debug UV map loaded |
| `variants/eyes-champney.py` | Two eyes spread 90 px wider, `CRAZY_EYES` on. The step before `tri-eyes.py` |

The files in `variants/` need to sit next to `gfxutil.py` and `graphics/`, so
copy one up into `/boot/Pi_Eyes/` before running it.

## Wifi

Bullseye uses `wpa_supplicant` and `dhcpcd`, not NetworkManager. Networks are
in `/etc/wpa_supplicant/wpa_supplicant.conf`, one `network={ ... }` block each.
The original Pi has two blocks, `SCN-IoT` and `TheInternet`.

To move to a new SSID without locking yourself out, **add** the new network
while the old one still works:

```sh
wpa_passphrase "NEW-SSID" | sudo tee -a /etc/wpa_supplicant/wpa_supplicant.conf
#   type the wifi password and press Enter; it is not echoed
sudo vi /etc/wpa_supplicant/wpa_supplicant.conf   # delete the "#psk=..." plaintext line
sudo wpa_cli -i wlan0 reconfigure
```

`sudo raspi-config` (System Options, Wireless LAN) does the same thing but
replaces rather than adds. Once the Pi is reachable on the new network, remove
the old block.

If it does fall off the network: plug in ethernet, or put the SD card in
another machine and drop a `wpa_supplicant.conf` into the boot partition. It
is copied into place on the next boot.

## Troubleshooting

| Symptom | Look at |
|---|---|
| Boot text, then a console login prompt, no eyes | `journalctl -b -u rc-local --no-pager \| tail -40`. A Python traceback there means `tri-eyes.py` crashed. |
| `ModuleNotFoundError` | A pip package is missing. Re-run `sudo ./install.sh`. |
| `failed to open vchiq instance` | `dtoverlay=vc4-fkms-v3d` is missing from `/boot/config.txt` (pi3d checks `lsmod` for `vc4`). |
| Desktop appears instead of eyes | `systemctl get-default` should say `multi-user.target`. |
| No picture at all | Cable must be in **HDMI0** (next to USB-C); the Pi only checks for a display at boot, so reboot after moving it. `tvservice -s` shows what the Pi is sending. |
| Projector says "no signal" but `tvservice -s` shows a mode | The projector rejects that timing. `edid-decode` on the output of `sudo tvservice -d /tmp/edid.dat` lists what it accepts; pick one of those with `hdmi_group`/`hdmi_mode`. |
| Picture goes dark after a while | `/etc/X11/xorg.conf` missing; re-run `install.sh`. |
| Slow or stuttering | `vcgencmd measure_temp; vcgencmd get_throttled`. Anything other than `throttled=0x0` means heat or power-supply trouble. |
| X server detail | `/var/log/Xorg.0.log` |
