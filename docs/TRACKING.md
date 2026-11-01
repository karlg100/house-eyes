# People tracking

A camera watches the sidewalk. The Intel Neural Compute Stick 2 (NCS2) finds
people in each frame, the tracker follows each of them, and the three eyes
watch them: all together when one person walks by, each eye on its own person
when there are several, and darting around when there's a crowd. When nobody
is in view, the eyes go back to wandering on their own.

```
camera ──> house_eyes_tracker.py ──────UDP──────> tri-eyes.py
           NCS2 person detector                   eases each eye toward its
           people.py: tracking with IDs,          point; wanders after 2 s
           attention, calibration                 of silence
```

The two programs are independent. If the tracker stops, crashes, or has no
camera, the eyes carry on exactly as before.

## Status (2026-10-08)

| Part | State |
|---|---|
| Gaze input in `tri-eyes.py` (one point, or one per eye, plus pupil size) | Done and running on the Pi |
| Multi-person tracking, attention, split eyes, crowd mode | Done; tested in simulation and on recorded video on the Pi |
| NCS2 + OpenVINO 2022.3.2 | Installed and working on the Pi |
| Tracker service | Installed, enabled, waiting for a camera |
| Camera | Not attached yet. Config is set for a Pi Camera Module (`source = picamera2`) |
| Calibration | Not done; needs the camera in its final position |

Tested end to end with a recorded video in place of the camera: people were
detected on the stick, and the projected eyes turned to follow them.

### Night test, 2026-10-30

- Camera: OV5647 NoIR, clip-on fisheye removed, tilted down to the yard.
  Settings on the Pi: `crop = 0,0.3,1,1`, `x_left = 0`, `x_right = 1`,
  `flip_x = yes`, `lost_after = 2.0`.
- IR: Univivi 20-LED 850 nm flood. The yard is visible at night but dim
  (about 3/255 at 120 ms and gain 12 before brightening).
- Result: detections at night are intermittent. A person in the yard was
  picked up for 1 to 3 seconds at a time; the sidewalk is too dark. Enabled
  as-is for Halloween: when someone is detected the eyes look their way, and
  otherwise they wander as usual.
- In daylight with the fisheye, the detector found a walker on the road in
  only 17% of frames (31% with the picture split in halves); motion picked
  them up reliably. A motion-plus-detector mode is the next improvement.

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
| Tracker | `/opt/house-eyes/tracker/house_eyes_tracker.py`, `people.py` |
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

**1. Detect.** Every frame goes to the stick, which returns a box per person.
People shorter than `min_height` or with their feet outside `roi` are ignored.

**2. Track.** `people.py` matches each box to a person seen in earlier frames,
using where they were heading, how much the boxes overlap, and how big they
are (people at different distances are different sizes). So two people passing
each other keep their own IDs, and someone briefly hidden behind another person
is remembered for `lost_after` seconds. A new person must be seen
`confirm_hits` times before they count, which filters out one-frame false
alarms.

**3. Decide who to watch.** It depends on how many people are in view:

| People | Mode | What the eyes do |
|---|---|---|
| 0 | idle | Nothing is sent; the eyes wander on their own |
| 1 | single | All three eyes watch that person together |
| 2 | split | The screen-left eye takes the left person, the screen-right eye the right person, and the centre eye picks whichever is more interesting, switching every few seconds |
| 3 to 6 | split | The three most interesting people each get an eye, ordered left to right so the eyes don't cross. Every `dwell_min` to `dwell_max` seconds an eye may move on to someone more interesting |
| `crowd_enter` (7) or more | crowd | Each eye darts between random people every `glance_min` to `glance_max` seconds, pupils wide. Back to split at `crowd_exit` (5) or fewer |

"Interesting" means: nearer (taller in the picture), newly arrived (fades over
a few seconds), or standing still to look (after a second). People the eyes
have already watched for a while become less interesting, so attention moves
around. When two watched people walk past each other, each eye stays with its
person; the eyes are only re-sorted if they'd stay crossed for more than a
second.

If anyone gets close (taller than `close_height` of the picture), the pupils
widen to `close_pupil`.

**4. Calibrate.** A person's horizontal position maps to gaze x through
`x_left` and `x_right`. How low their feet are in the frame maps to gaze y
through `y_at_top` and `y_at_bottom`. The eyes aim a little ahead of a walking
person (`lead`) to hide the camera and detector delay.

**5. Send.** About 15 times a second while anyone is in view, the tracker sends
`tri-eyes.py` either `x y` (all eyes on one point) or `xl yl xc yc xr yr` (one
point per eye, screen-left to screen-right), optionally followed by `p=0.9` for
the pupil size.

### Simulation

`tracker/sim_people.py` exercises the tracking and attention logic with
simulated pedestrians, without a camera or the stick. It runs anywhere Python 3
does:

```sh
cd tracker && python3 sim_people.py        # add -v to print what's sent each second
```

It reports, per scenario (one walker, 4 spread out with 2 standing, 2
crossing, a busy sidewalk, a crowd of about 25): mode changes, how often each
eye switches person, ID swaps, and how often the eyes are crossed. Use it to
check the effect of changing the `[attention]` defaults before trying them on
the street.

## Calibrating (once the camera is mounted)

1. On a phone or laptop on the home network, open **http://eyes.local:8080/**.
   It shows the camera view with a box on each person, labelled with their ID
   and horizontal position (`x=0.42`). Coloured dots show which eye watches
   them (red = screen-left eye, green = centre, blue = screen-right). The blue
   frame is the region of interest, and the markers on the top bar show where
   each eye is being told to look. The current mode and number of people are
   in the top-left corner.
2. If the picture is upside down or mirrored, set `rotate` / `hflip` under
   `[camera]`.
3. Stand at the far left of the sidewalk stretch you care about and read your
   `x=` value off your box (0 = left edge of the picture, 1 = right edge). Put
   that number in `x_left`. Do the same at the far right for `x_right`.
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
echo "-1 0 0 0.8 1 0 p=1" | nc -u -w0 eyes.local 5005   # left eye left, centre up, right eye right, pupils wide
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
Pi. `face-demographics-walking-and-pause.mp4` has people coming and going
(single and split modes), `classroom.mp4` has 4 people at once (split), and
`crowd-tiled.mp4` is six clips tiled together to reach crowd mode. Its tiling
makes some boxes span two tiles, so it's only good for exercising the modes.
`~/vidtest.sh VIDEO SECONDS TAG` runs one and saves preview and eye
screenshots to `/tmp`. Add `--no-send` to track without moving the eyes, or `--detector motion`
to try the CPU fallback.

## Other cameras

Set `source` under `[camera]`:

| Camera | Setting |
|---|---|
| Pi Camera Module on the ribbon connector | `picamera2` |
| USB webcam | `usb:0` |
| Network camera | `rtsp://user:password@192.168.1.x/...` (expect a second or more of lag) |
| Recorded video, looped | `file:/path/to/video.mp4` |

## Link to the show controller (added 2026-11-01)

The front-lawn show controller (the "haunt" director on home-pi, repo
rpiGridMultiTask) can now switch tracking on and off, and shows whether the
eyes are online and how many people they see (console `e`, phone page
"House eyes" card). The controller side is deployed and live.

How it works (tracker/showlink.py, optional `[show]` section in tracker.ini):

- MQTT, broker 192.168.1.244, user `home-pi`, prefix `haunt`.
- In: `haunt/eyes/tracking/set`, retained, `1` / `0`. With `0` the tracker
  keeps detecting but sends no gaze messages, so tri-eyes.py wanders on its
  own (its 2 s fallback). The retained value applies as soon as the tracker
  connects.
- Out: `haunt/eyes/online` (retained, `1`, last will `0`) and
  `haunt/eyes/status` (retained JSON every 2 s and on change: tracking,
  people, mode, camera_fps, detector_fps, host, ts).
- No `[show]` host, or no paho-mqtt installed = runs exactly as before
  (tracking always on).
- Tests: `python3 -m pytest tracker/test_showlink.py` (no broker needed).

### Installing it on eyes.local (NOT DONE YET)

The controller session could not log in to eyes.local (its key,
`claude-cowork-haunt`, is not authorized there), so this is still to do:

```sh
sudo apt install python3-paho-mqtt
sudo install -m 644 tracker/showlink.py tracker/house_eyes_tracker.py tracker/people.py /opt/house-eyes/tracker/
sudo install -m 644 tracker/house-eyes-tracker.service /etc/systemd/system/    # now reads EnvironmentFile=-/etc/house-eyes/env
# add the [show] section from tracker/tracker.ini.example to /etc/house-eyes/tracker.ini
# (host 192.168.1.244, port 1883, username home-pi, prefix haunt)
sudo sh -c 'umask 077; echo "HAUNT_MQTT_PASSWORD=<same as /etc/haunt/env on home-pi>" > /etc/house-eyes/env'
sudo systemctl daemon-reload && sudo systemctl restart house-eyes-tracker
journalctl -u house-eyes-tracker -n 20     # expect "show link: connected"
```

Then check from the controller: the console shows an "Eyes" line (TRACKING,
people in view), and pressing `e` there logs "tracking OFF (from the show
controller)" here. Compare /opt/house-eyes/tracker with the repo first in case
the Pi has local changes.

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
| Eyes switch people too often | Raise `dwell_min` / `dwell_max`, lower `newcomer_bonus`, narrow `roi` |
| Crowd mode kicks in too easily, or not at all | Adjust `crowd_enter` / `crowd_exit` |
| Pupils stay wide | `close_height` is too low for your camera view; raise it, or set 0 to turn off |
| Eyes look half-closed | Gaze y is far down, and the eyelids follow the pupils. Raise `y_at_top` / `y_at_bottom` (closer to 0) |
| Eyes lag behind walkers | Raise `lead` a little (0.2 to 0.3) |
