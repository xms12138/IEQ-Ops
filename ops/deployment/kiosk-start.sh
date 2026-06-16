#!/usr/bin/env bash
# IEQ-Ops exhibit kiosk launcher — full-screen Chromium under the cage Wayland
# compositor, pointed at the local dashboard. Driven by ieq-kiosk.service on boot.
#
# No display attached yet? cage needs a DRM connector (a plugged-in screen) to bring up
# an output; until then the service just restarts. Plug in the touchscreen + reboot (or
# `sudo systemctl restart ieq-kiosk`) and the dashboard fills the screen.
#
# The browser talks to the dashboard over localhost, which is a "secure context", so the
# mic works with no tunnel — that is the whole point of running the browser ON the Pi.
set -euo pipefail

URL="${IEQ_KIOSK_URL:-http://localhost:8000/kiosk}"

exec cage -- chromium \
  --kiosk \
  --app="$URL" \
  --noerrdialogs \
  --disable-infobars \
  --no-first-run \
  --disable-session-crashed-bubble \
  --disable-features=Translate \
  --autoplay-policy=no-user-gesture-required \
  --check-for-update-interval=31536000 \
  --password-store=basic
