#!/usr/bin/env bash
# Usage: bash deploy_fix.sh /path/to/downloaded/test_generator.py
# Example: bash deploy_fix.sh ~/Downloads/test_generator.py

set -e

DEST="/home/nabakumr/Videos/OpsMindAI-final/OpsMindAI-server/opsmindai/agents/testing/test_generator.py"
PYC="/home/nabakumr/Videos/OpsMindAI-final/OpsMindAI-server/opsmindai/agents/testing/__pycache__/test_generator.cpython-312.pyc"
SERVER="/home/nabakumr/Videos/OpsMindAI-final/OpsMindAI-server"

# Check argument
if [ -z "$1" ]; then
    echo "Usage: bash deploy_fix.sh /path/to/test_generator.py"
    exit 1
fi

SRC="$1"

if [ ! -f "$SRC" ]; then
    echo "ERROR: File not found: $SRC"
    exit 1
fi

echo "==> Copying $SRC  -->  $DEST"
cp "$SRC" "$DEST"
echo "    OK"

echo "==> Removing stale .pyc ..."
rm -f "$PYC"
echo "    OK"

echo "==> Killing existing Celery testing workers ..."
pkill -f "celery.*testing" 2>/dev/null && echo "    Killed" || echo "    (none running)"
sleep 2

echo "==> Starting Celery worker ..."
cd "$SERVER"
source myenv/bin/activate
nohup celery -A opsmindai.tasks.celery_app worker \
    --loglevel=info \
    -Q testing \
    -n test@%h > /tmp/celery_testing.log 2>&1 &

echo ""
echo "==> Done!  Worker PID: $!"
echo "    Watch logs:  tail -f /tmp/celery_testing.log"