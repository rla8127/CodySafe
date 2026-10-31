#!/usr/bin/env bash
# CodySafe GPU warm-up for rehearsal/demo.
#   gpu/warm.sh up     -> keep 1 container warm in each app (codysafe-llm, codysafe-voice[, codysafe-video])
#   gpu/warm.sh down   -> back to 0 (scale to zero after the 5-minute idle window)
#   gpu/warm.sh status -> list running containers
#
# COST: "up" bills GPU time every hour until "down" runs (L40S about US$1.95/h per app, 2 apps about
# US$3.9/h). Credit is US$30 with spend limit $0: when it runs out Modal stops the apps.
# Always run "down" right after the demo. 김호연 decides when to run "up".
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-.venv/bin/python}"
N=0
case "${1:-}" in
  up) N=1 ;;
  down) N=0 ;;
  status) exec "${PY%/python}/modal" container list ;;
  *) echo "usage: $0 up|down|status" >&2; exit 2 ;;
esac
"$PY" - "$N" <<'EOF'
import sys
import modal

n = int(sys.argv[1])
targets = [("codysafe-llm", "serve", None), ("codysafe-voice", None, "Voice"), ("codysafe-video", None, "Video")]
for app, fn, cls in targets:
    try:
        obj = modal.Function.from_name(app, fn) if fn else modal.Cls.from_name(app, cls)()
        obj.update_autoscaler(min_containers=n)
        print(f"{app}: min_containers={n}")
    except modal.exception.NotFoundError:
        print(f"{app}: not deployed, skipped")
EOF
if [ "$N" = 1 ]; then
  echo "Containers are starting (cold start: see eval/gpu_latency.md). Run '$0 down' after the demo."
fi
