#!/bin/bash
# house-eyes installer
#
# Turns a fresh Raspberry Pi OS (bullseye, 32-bit, Desktop) install on a
# Raspberry Pi 4 into the three-eyed house projector: on every boot it goes
# straight into eyes/tri-eyes.py, full screen on HDMI, no desktop, no login.
#
# This is a non-interactive rewrite of what Adafruit's pi-eyes.sh did on the
# original box (Pi 4 + HDMI answers) plus the manual changes made afterwards.
# Safe to re-run: it re-copies the eye code and re-applies the same settings.
#
#   sudo ./install.sh            install / update, then reboot yourself
#   sudo EYES=cyclops.py ./install.sh    boot a different eye program

set -euo pipefail

EYES="${EYES:-tri-eyes.py}"       # program started at boot (file in eyes/)
DEST=/boot/Pi_Eyes                # where the running copy lives
CONFIG=/boot/config.txt
REPO="$(cd "$(dirname "$0")" && pwd)"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo $0" >&2; exit 1
fi
if [ ! -f "$REPO/eyes/$EYES" ]; then
  echo "No such eye program: eyes/$EYES" >&2; exit 1
fi
. /etc/os-release
if [ "${VERSION_CODENAME:-}" != "bullseye" ]; then
  echo "WARNING: built and tested on Raspberry Pi OS 11 (bullseye); this is ${PRETTY_NAME:-unknown}." >&2
  echo "         Newer releases moved /boot and block system-wide pip. Continuing in 5s..." >&2
  sleep 5
fi
if ! command -v Xorg >/dev/null; then
  echo "Xorg not found. Use the Desktop image, not Lite (pi3d on a Pi 4 needs X)." >&2; exit 1
fi

echo "== Packages"
apt-get update
apt-get install -y python3-pip python3-dev python3-pil python3-numpy \
  python3-smbus python3-rpi.gpio libatlas-base-dev xinit
# Versions pinned to what the original box runs.
pip3 install pi3d==2.49 svg.path==6.3 \
  Adafruit-Blinka==8.20.0 adafruit-circuitpython-ads1x15==2.2.22

echo "== Eye code -> $DEST"
mkdir -p "$DEST"
cp -r "$REPO/eyes/." "$DEST/"

echo "== Boot to console, not the desktop"
systemctl set-default multi-user.target
ln -fs /lib/systemd/system/getty@.service \
  /etc/systemd/system/getty.target.wants/getty@tty1.service
rm -f /etc/systemd/system/getty@tty1.service.d/autologin.conf

echo "== $CONFIG"
[ -f "$CONFIG.house-eyes.orig" ] || cp "$CONFIG" "$CONFIG.house-eyes.orig"
# Append a line so it applies to every Pi model (i.e. under an [all] filter).
append_all() {
  if [ "$(grep -E '^\[' "$CONFIG" | tail -n 1)" != "[all]" ]; then
    printf '\n[all]\n' >> "$CONFIG"
  fi
  printf '%s\n' "$1" >> "$CONFIG"
}
# Set key=value: reuse an existing (possibly commented-out) line, else append.
set_config() {
  if grep -qE "^#? *$1=" "$CONFIG"; then
    sed -i -E "s|^#? *$1=.*|$1=$2|" "$CONFIG"
  else
    append_all "$1=$2"
  fi
}
# pi3d needs the "fake" KMS driver, not the default full KMS one.
if ! grep -q '^dtoverlay=vc4-fkms-v3d' "$CONFIG"; then
  if grep -q '^dtoverlay=vc4-kms-v3d' "$CONFIG"; then
    sed -i -E 's|^dtoverlay=vc4-kms-v3d.*|#&\ndtoverlay=vc4-fkms-v3d|' "$CONFIG"
  else
    append_all "dtoverlay=vc4-fkms-v3d"
  fi
fi
set_config max_framebuffers 1
set_config disable_overscan 1
set_config gpu_mem 128
# Boot HDMI mode: standard DMT 640x480 @ 60 Hz (group 2, mode 4).
# The old custom mode (mode 87 + hdmi_cvt) came out at ~29.7 kHz, below what
# the Hichip projector accepts (31-135 kHz) -> "no signal". Fixed 2026-10-08.
set_config hdmi_group 2
set_config hdmi_mode 4
sed -i -E 's|^hdmi_cvt=|#hdmi_cvt=|' "$CONFIG"
# Drive HDMI even if the projector is off or asleep when the Pi boots.
set_config hdmi_force_hotplug 1

echo "== X: never blank the screen"
cat > /etc/X11/xorg.conf <<'XORG'
Section "ServerFlags"
  Option "BlankTime" "0"
  Option "StandbyTime" "0"
  Option "SuspendTime" "0"
  Option "OffTime" "0"
  Option "dpms" "false"
EndSection
XORG

echo "== Start $EYES at boot (/etc/rc.local)"
sed -i '/Pi_Eyes/d' /etc/rc.local
sed -i "s|^exit 0|cd $DEST;xinit /usr/bin/python3 $EYES :0 \&\nexit 0|" /etc/rc.local
chmod +x /etc/rc.local
grep -q "Pi_Eyes" /etc/rc.local || { echo "Could not add start line to /etc/rc.local" >&2; exit 1; }

echo
echo "Done. Reboot to start the eyes:  sudo reboot"
