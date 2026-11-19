#!/usr/bin/env bash
# One-time privileged installer and full run. No sudoers or sudo policy edits.
set -euo pipefail

PROJECT='/home/harikrishna/cn-demo/Team1_Project11_Remote_System_Health_Monitoring'
RUNTIME='/opt/cn-project11'
LAUNCHER='/usr/local/sbin/cn11-demo'
STAGE=''
LAUNCHER_STAGE=''
RUNTIME_PUBLISHED=0

cleanup_staging() {
    if [[ -n "$STAGE" && "$STAGE" == /opt/.cn-project11-stage.* && -d "$STAGE" ]]; then
        rm -rf -- "$STAGE"
    fi
    if [[ -n "$LAUNCHER_STAGE" && "$LAUNCHER_STAGE" == /usr/local/sbin/.cn11-demo-stage.* && -f "$LAUNCHER_STAGE" ]]; then
        rm -f -- "$LAUNCHER_STAGE"
    fi
    if [[ "$RUNTIME_PUBLISHED" -eq 1 && ! -e "$LAUNCHER" && -d "$RUNTIME" ]]; then
        rm -rf -- "$RUNTIME"
    fi
}

if [[ "${EUID}" -ne 0 ]]; then
    echo 'Run this installer interactively with sudo.' >&2
    exit 2
fi

if [[ -e "$RUNTIME" || -e "$LAUNCHER" ]]; then
    echo "Refusing to overwrite existing installation: $RUNTIME or $LAUNCHER" >&2
    exit 3
fi
trap cleanup_staging EXIT

if [[ -L "$PROJECT" || "$(readlink -e -- "$PROJECT")" != "$PROJECT" ]]; then
    echo "Project path is not the expected real directory: $PROJECT" >&2
    exit 4
fi

files=(
    agents.py
    monitor.py
    controller.py
    topology.py
    CN_Project11_Verifier.py
    CN11_Demo_Runner.py
    start_controller.sh
    start_network.sh
    requirements.txt
)

for name in "${files[@]}"; do
    if [[ ! -f "$PROJECT/$name" || -L "$PROJECT/$name" ]]; then
        echo "Required regular, non-symlink project file missing: $PROJECT/$name" >&2
        exit 4
    fi
    resolved=$(readlink -e -- "$PROJECT/$name")
    case "$resolved" in
        "$PROJECT"/*) ;;
        *) echo "Refusing source outside project directory: $PROJECT/$name" >&2; exit 4 ;;
    esac
done

STAGE=$(mktemp -d /opt/.cn-project11-stage.XXXXXX)
chown root:root "$STAGE"
chmod 0755 "$STAGE"
for name in "${files[@]}"; do
    install -o root -g root -m 0644 "$PROJECT/$name" "$STAGE/$name"
done

LAUNCHER_STAGE=$(mktemp /usr/local/sbin/.cn11-demo-stage.XXXXXX)
cat > "$LAUNCHER_STAGE" <<'LAUNCHER_EOF'
#!/bin/sh
set -eu
if [ "$#" -ne 0 ]; then
    echo 'This fixed-scope launcher accepts no arguments.' >&2
    exit 64
fi
exec /usr/bin/env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin HOME=/root LANG=C.UTF-8 /usr/bin/python3 -I /opt/cn-project11/CN11_Demo_Runner.py
LAUNCHER_EOF

chown root:root "$LAUNCHER_STAGE"
chmod 0755 "$LAUNCHER_STAGE"

mv -- "$STAGE" "$RUNTIME"
STAGE=''
RUNTIME_PUBLISHED=1
mv -- "$LAUNCHER_STAGE" "$LAUNCHER"
LAUNCHER_STAGE=''
RUNTIME_PUBLISHED=0
trap - EXIT

echo 'Installed root-owned runtime snapshot and fixed-purpose launcher.'
echo 'No sudoers files, sudo defaults, or authentication settings were changed.'
echo 'Starting the full verification workflow now.'
exec "$LAUNCHER"
