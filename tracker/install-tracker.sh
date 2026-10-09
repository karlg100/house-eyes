#!/bin/bash
# house-eyes tracker installer
#
# Adds people tracking to a Pi already set up with ../install.sh:
#   - Intel OpenVINO 2022.3.2 runtime (last release that supports the
#     Neural Compute Stick 2) in /opt/intel, plus the stick's udev rule
#   - the person-detection model in /opt/house-eyes/models
#   - the tracker in /opt/house-eyes/tracker, config in /etc/house-eyes
#   - house-eyes-tracker.service, running as the "house-eyes" user
#   - arm_64bit=0 in /boot/config.txt (32-bit kernel; see docs/TRACKING.md)
#
# Safe to re-run; an existing /etc/house-eyes/tracker.ini is never replaced.
#
#   sudo ./tracker/install-tracker.sh

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CONFIG=/boot/config.txt

OV_VER=2022.3.2
OV_NAME=l_openvino_toolkit_debian9_2022.3.2.9279.e2c7e4d7b4d_armhf
OV_URL=https://storage.openvinotoolkit.org/repositories/openvino/packages/$OV_VER/linux/$OV_NAME.tgz
OV_SHA256=9e78f6025750c9cf0e2112c4ecc76231030517797014227a02eaa2b1dff7178d

MODEL=person-detection-retail-0013
MODEL_URL=https://storage.openvinotoolkit.org/repositories/open_model_zoo/2022.3/models_bin/1/$MODEL/FP16
MODEL_XML_SHA256=466744938e810e1154c7094503e67971773c1e0bc60c44fbf946ba77508a2efc
MODEL_BIN_SHA256=4f7b51a97be06dbd6f4171832b3413e56bae3e71b89f60f3579949635ae53534

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo $0" >&2; exit 1
fi
if [ "$(dpkg --print-architecture)" != "armhf" ]; then
  echo "This needs the 32-bit (armhf) Raspberry Pi OS; found $(dpkg --print-architecture)." >&2
  exit 1
fi

fetch() {  # url dest sha256
  local tmp; tmp="$(mktemp)"
  curl -fsSL -o "$tmp" "$1"
  echo "$3  $tmp" | sha256sum -c --quiet - || { echo "Checksum mismatch: $1" >&2; rm -f "$tmp"; exit 1; }
  install -m 644 "$tmp" "$2"; rm -f "$tmp"
}

echo "== Packages"
apt-get update
apt-get install -y python3-opencv python3-numpy python3-picamera2 curl

echo "== OpenVINO $OV_VER runtime"
if [ ! -f "/opt/intel/$OV_NAME/setupvars.sh" ]; then
  mkdir -p /opt/intel
  fetch "$OV_URL" "/opt/intel/$OV_NAME.tgz" "$OV_SHA256"
  tar xzf "/opt/intel/$OV_NAME.tgz" -C /opt/intel
  rm -f "/opt/intel/$OV_NAME.tgz"
fi
ln -sfn "$OV_NAME" /opt/intel/openvino_2022
install -m 644 /opt/intel/openvino_2022/install_dependencies/97-myriad-usbboot.rules /etc/udev/rules.d/
udevadm control --reload-rules
udevadm trigger --subsystem-match=usb --action=add

echo "== Model"
mkdir -p /opt/house-eyes/models
[ -f /opt/house-eyes/models/$MODEL.xml ] || fetch "$MODEL_URL/$MODEL.xml" /opt/house-eyes/models/$MODEL.xml "$MODEL_XML_SHA256"
[ -f /opt/house-eyes/models/$MODEL.bin ] || fetch "$MODEL_URL/$MODEL.bin" /opt/house-eyes/models/$MODEL.bin "$MODEL_BIN_SHA256"

echo "== Tracker"
id house-eyes >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin house-eyes
usermod -a -G video,users house-eyes
mkdir -p /opt/house-eyes/tracker /etc/house-eyes
install -m 755 "$HERE/house_eyes_tracker.py" /opt/house-eyes/tracker/
install -m 644 "$HERE/tracker.ini.example" /etc/house-eyes/tracker.ini.example
[ -f /etc/house-eyes/tracker.ini ] || install -m 644 "$HERE/tracker.ini.example" /etc/house-eyes/tracker.ini
install -m 644 "$HERE/house-eyes-tracker.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable house-eyes-tracker.service

echo "== 32-bit kernel"
REBOOT=0
if ! grep -q '^arm_64bit=0' "$CONFIG"; then
  [ -f "$CONFIG.pre-tracker" ] || cp "$CONFIG" "$CONFIG.pre-tracker"
  printf '\n[all]\n# 32-bit kernel: OpenVINO (armhf) needs alignment fixups the arm64 kernel lacks\narm_64bit=0\n' >> "$CONFIG"
  REBOOT=1
fi

if [ "$REBOOT" -eq 1 ]; then
  echo; echo "Done. Reboot to switch to the 32-bit kernel; the tracker starts on boot."
else
  systemctl restart house-eyes-tracker.service
  echo; echo "Done. Tracker restarted:  journalctl -u house-eyes-tracker -f"
fi
echo "Calibration view: http://$(hostname).local:8080/"
