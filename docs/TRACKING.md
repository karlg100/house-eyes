# People tracking

A camera watches the sidewalk. The Intel Neural Compute Stick 2 (NCS2) finds
people in each frame, the tracker picks one, and the three eyes turn to follow
them as they walk past. When nobody is in view, the eyes go back to wandering
on their own.

```
camera ──> house_eyes_tracker.py ──UDP "x y"──> tri-eyes.py
           (NCS2 person detector,               (eases toward the point;
            target picking, calibration)          wanders after 2 s of silence)
```

The two programs are independent. If the tracker stops, crashes, or has no
camera, the eyes carry on exactly as before.

## Status (2026-10-08)

| Part | State |
|---|---|
| Gaze input in `tri-eyes.py` | Done and running on the Pi |
| NCS2 + OpenVINO 2022.3.2 | Installed and working on the Pi |
| Tracker service | Installed, enabled, waiting for a camera |
| Camera | Not attached yet. Config is set for a Pi Camera Module (`source = picamera2`) |
| Calibration | Not done; needs the camera in its final position |

Tested end to end with a recorded video in place of the camera: people were
detected on the stick, and the projected eyes turned to follow them.

## Installing

On a Pi already set up with `./install.sh`:

```sh
cd ~/house-eyes
sudo ./install.sh                     # also deploys the gaze-enabled tri-eyes.py
sudo ./tracker/install-tracker.sh
sudo reboot                           # only needed the first time (32-bit kernel)
```

`install-tracker.sh` puts these in place:

| What | Where |
|---|---|
| OpenVINO 2022.3.2 runtime (armhf), checksum-verified | `/opt/intel/l_openvino_toolkit_debian9_2022.3.2...`, symlinked as `/opt/intel/openvino_2022` |
| NCS2 udev rule | `/etc/udev/rules.d/97-myriad-usbboot.rules` |
| `person-detection-retail-0013` model (FP16), checksum-verified | `/opt/house-eyes/models/` |
| Tracker | `/opt/house-eyes/tracker/house_eyes_tracker.py` |
| Settings | `/etc/house-eyes/tracker.ini` (never overwritten on re-install) |
| Service | `house-eyes-tracker.service`, runs as user `house-eyes` |
| Kernel | `arm_64bit=0` in `/boot/config.txt` (see below) |

## Why the 32-bit kernel

OpenVINO 2022.3 is the last release that supports the NCS2, and its Raspberry
Pi build is 32-bit (armhf). The Pi 4 boots a 64-bit kernel by default, and
that kernel (`6.1.21-v8+`) is built without `CONFIG_COMPAT_ALIGNMENT_FIXUPS`.
OpenVINO's model compiler does unaligned memory accesses that a 32-bit kernel
quietly fixes up, but the 64-bit kernel kills the program with a **bus
error** instead. `arm_64bit=0` boots the Pi's 32-bit kernel (`6.1.21-v7l+`),
which is what Intel tested on. The eyes run the same on either kernel.

Don't upgrade the OS to bookworm or later: OpenVINO 2022.3 won't install there,
and the eyes setup depends on bullseye.

## Performance (measured on the Pi, 2026-10-08)

| Setup | Speed |
|---|---|
| NCS2, one request at a time | about 7.6 detections/s |
| NCS2, 2 to 4 requests in parallel (what the tracker does) | about 14 to 15 detections/s |
| Pi CPU with OpenVINO, same model | about 0.5 detections/s |

The stick is currently plugged in through a USB 2 path. A blue USB 3 port may
help a little; not measured.

## How the tracker decides where to look

1. **Detect.** Every frame goes to the stick. People below `min_height` or
   with their feet outside `roi` are ignored.
2. **Pick.** The tallest person (nearest) becomes the target. The tracker stays
   with them until they're out of view for `lost_after` seconds. It won't jump
   to someone else for `switch_after` seconds unless the target is lost.
3. **Smooth and lead.** The position is eased (`smooth`), and the eyes aim a
   little ahead of a walking person (`lead`) to hide the camera and detector
   delay.
4. **Calibrate.** Horizontal camera position maps to gaze x through `x_left`
   and `x_right`. How low the person's feet are in the frame maps to gaze y
   through `y_at_top` and `y_at_bottom`.
5. **Send.** `x y` (each -1 to 1) goes over UDP to `tri-eyes.py` on port 5005,
   15 times a second while there's a target. Nothing is sent when there isn't.

## Calibrating (once the camera is mounted)

1. On a phone or laptop on the home network, open **http://eyes.local:8080/**.
   It shows the camera view with boxes on detected people (green = being
   watched), the region of interest (blue), and a red marker on the top bar
   showing where the eyes are being told to look.
2. If the picture is upside down or mirrored, set `rotate` / `hflip` under
   `[camera]`.
3. Stand at the far left of the sidewalk stretch you care about and note the
   red dot's x position (0 = left edge, 1 = right edge). Put that number in
   `x_left`. Do the same at the far right for `x_right`.
4. Walk past. If the eyes turn the opposite way, set `flip_x = yes`. This is
   needed if the projector is mirrored for rear projection, or the camera faces
   the other way.
5. Adjust `y_at_top` / `y_at_bottom` until the eyes look down at people rather
   than over their heads.
6. If cars, trees or reflections get picked up, shrink `roi` to the sidewalk,
   or raise `confidence`.

After each edit:

```sh
sudo nano /etc/house-eyes/tracker.ini
sudo systemctl restart house-eyes-tracker
```

## Testing without a camera

Move the eyes by hand, from the Pi or any machine on the network:

```sh
echo "1 0"   | nc -u -w0 eyes.local 5005    # look screen-right
echo "-1 0"  | nc -u -w0 eyes.local 5005    # look screen-left
echo "0 -0.6" | nc -u -w0 eyes.local 5005   # look down
```

Each message holds for 2 seconds, then the eyes wander again.

Run the tracker on a recorded video:

```sh
sudo systemctl stop house-eyes-tracker     # only one program can use the stick
source /opt/intel/openvino_2022/setupvars.sh
python3 /opt/house-eyes/tracker/house_eyes_tracker.py \
    --source file:/home/karlg/testvids/one-by-one-person-detection.mp4
# Ctrl-C to stop, then:
sudo systemctl start house-eyes-tracker
```

Test videos from Intel's `sample-videos` repository are in `~/testvids` on the
Pi. Add `--no-send` to track without moving the eyes, or `--detector motion`
to try the CPU fallback.

## Other cameras

Set `source` under `[camera]`:

| Camera | Setting |
|---|---|
| Pi Camera Module on the ribbon connector | `picamera2` |
| USB webcam | `usb:0` |
| Network camera | `rtsp://user:password@192.168.1.x/...` (expect a second or more of lag) |
| Recorded video, looped | `file:/path/to/video.mp4` |

## Operations

```sh
systemctl status house-eyes-tracker
journalctl -u house-eyes-tracker -f          # live log; a stats line every 30 s
sudo systemctl restart house-eyes-tracker
sudo systemctl disable --now house-eyes-tracker   # turn tracking off entirely
```

## Troubleshooting

| Log message | Meaning / fix |
|---|---|
| `no CSI camera detected; retrying` | No Pi camera found. Check the ribbon is fully seated with the latch closed at both ends, then reboot. `libcamera-hello --list-cameras` should list it |
| `waiting for the Neural Compute Stick...` | Normal for a few seconds after a restart while the stick re-boots. If it never clears, check `lsusb` shows `03e7:2485` or `03e7:f63b` |
| `ncDeviceOpen ... global mutex initialization failed` | A stale `/tmp/mvnc.mutex` from a run as another user. The service uses a private `/tmp`, so this only affects manual runs; `sudo rm /tmp/mvnc.mutex` |
| `Bus error` | Running on the 64-bit kernel. Check `uname -r` ends in `-v7l+` and `arm_64bit=0` is in `/boot/config.txt` |
| Eyes look the wrong way | `flip_x = yes` |
| Eyes jitter between people | Raise `switch_after` or `smooth`, narrow `roi` |
| Eyes lag behind walkers | Raise `lead` a little (0.2 to 0.3) |
