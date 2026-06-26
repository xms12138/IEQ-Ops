#!/usr/bin/env bash
# ops/scripts/dry_run_monitor.sh — periodic health sampler for the unattended dry-run.
#
# Writes one CSV line per INTERVAL to var/dry_run.log, so over a 72 h run a memory leak
# shows up as monotonically rising RSS and a crash shows up as a bumped NRestarts. Cheap
# (a few shell-outs every 10 min). Start it as a transient service so it survives ssh
# logout (runs as the xms12138 user so psql/journal/proc access all work):
#
#   sudo systemd-run --unit=ieq-drymon --uid=1000 --gid=1000 \
#        -p Environment=HOME=/home/xms12138 \
#        /home/xms12138/dissertation/ops/scripts/dry_run_monitor.sh
#   sudo systemctl stop ieq-drymon         # to end it
#   column -t -s, ~/dissertation/var/dry_run.log | less   # to read the trend
#
set -uo pipefail
LOG="${HOME}/dissertation/var/dry_run.log"
INTERVAL="${IEQ_DRYRUN_INTERVAL:-600}"
mkdir -p "$(dirname "$LOG")"
[ -s "$LOG" ] || echo "ts,mem_used_mb,mem_avail_mb,swap_mb,web_rss_mb,sched_rss_mb,web_restarts,sched_restarts,kiosk_restarts,web_active,sched_active,kiosk_active,err_window" >> "$LOG"

rss_mb() { local p="${1:-}"; { [ -n "$p" ] && [ "$p" != 0 ] && awk '/VmRSS/{print int($2/1024)}' "/proc/$p/status"; } 2>/dev/null || echo 0; }
val()    { systemctl show -p "$2" --value "$1" 2>/dev/null || echo NA; }

while true; do
  ts=$(date -Is)
  mu=$(free -m | awk '/^Mem:/{print $3}'); ma=$(free -m | awk '/^Mem:/{print $7}'); sw=$(free -m | awk '/^Swap:/{print $3}')
  wr=$(rss_mb "$(val ieq-web MainPID)"); sr=$(rss_mb "$(val ieq-scheduler MainPID)")
  since=$(date -d "-${INTERVAL} seconds" '+%Y-%m-%d %H:%M:%S')
  err=$(journalctl -q --since "$since" -p err -u ieq-web -u ieq-scheduler -u ieq-kiosk --no-pager 2>/dev/null | grep -vcE '^(-- |$)')
  echo "$ts,$mu,$ma,$sw,$wr,$sr,$(val ieq-web NRestarts),$(val ieq-scheduler NRestarts),$(val ieq-kiosk NRestarts),$(val ieq-web ActiveState),$(val ieq-scheduler ActiveState),$(val ieq-kiosk ActiveState),$err" >> "$LOG"
  sleep "$INTERVAL"
done
