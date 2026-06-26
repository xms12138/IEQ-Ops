#!/usr/bin/env bash
# ops/deployment/setup-audio.sh — one-time audio + emoji-font setup for the Pi kiosk.
#
# The Debian 13 *Lite* image ships NO user-level sound server and NO colour-emoji
# font, so out of the box Chromium (running under cage/Wayland) cannot reach the USB
# microphone / 3.5 mm speaker and renders 🎤 as a tofu box. Run this once on the Pi
# (after the kiosk is up) to make the cascade-voice butler work on real hardware.
#
# Idempotent — re-running is safe. Verified on the exhibit Pi 2026-06-26 (DEVLOG P-033).
#
#   scp ops/deployment/setup-audio.sh pi:~/ && ssh pi 'bash ~/setup-audio.sh'
#
set -euo pipefail

echo "== 1/3  installing PipeWire stack + colour-emoji font =="
sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  pipewire pipewire-pulse wireplumber pipewire-audio pulseaudio-utils \
  fonts-noto-color-emoji
fc-cache -f >/dev/null

echo "== 2/3  enabling PipeWire as user services (linger keeps them across the kiosk session) =="
loginctl enable-linger "$USER"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
systemctl --user daemon-reload
systemctl --user enable --now pipewire.socket pipewire-pulse.socket wireplumber.service

echo "== 3/3  default devices (wireplumber auto-selects USB mic + 3.5 mm jack) =="
pactl get-default-sink   || true
pactl get-default-source || true
pactl list short sinks   || true
pactl list short sources || true

cat <<'NOTE'

== done ==
Expected: default source = USB mic, default sink = 3.5 mm jack
(alsa_output.platform-*.mailbox.*). If wireplumber picked the wrong ones:
  pactl set-default-sink   <sink-name>
  pactl set-default-source <source-name>
  pactl set-sink-volume    <sink-name>   85%   # unmute + level if silent
  pactl set-source-volume  <source-name> 80%

IMPORTANT: Chromium probes the audio backend only at launch, so it MUST be
restarted AFTER this script to pick up PipeWire:
  sudo systemctl restart ieq-kiosk
NOTE
