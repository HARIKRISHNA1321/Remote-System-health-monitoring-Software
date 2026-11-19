#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if ! command -v mn >/dev/null 2>&1; then
    echo "ERROR: Mininet is not installed."
    echo "Install it using: sudo apt install mininet"
    exit 1
fi

if ! command -v ovs-vsctl >/dev/null 2>&1; then
    echo "ERROR: Open vSwitch is not installed."
    echo "Install it using: sudo apt install openvswitch-switch"
    exit 1
fi

if ! sudo ovs-vsctl show >/dev/null 2>&1; then
    echo "ERROR: Open vSwitch is not running."
    echo "Try: sudo service openvswitch-switch start"
    exit 1
fi

echo "Starting Project 11 Mininet Network..."
echo "QoS and monitoring services will be configured automatically."

exec sudo python3 "$PROJECT_DIR/topology.py"
