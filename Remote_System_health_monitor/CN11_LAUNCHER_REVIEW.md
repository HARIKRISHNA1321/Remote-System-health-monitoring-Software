# Fixed-scope launcher: review before installation

## What it installs

`install_cn11_launcher.sh` installs the following:

- A root-owned, read-only runtime snapshot at `/opt/cn-project11` containing the project's Python sources and scripts needed by the runner.
- A root-owned executable `/usr/local/sbin/cn11-demo` that accepts no arguments and starts only `/opt/cn-project11/CN11_Demo_Runner.py`.

The installer stages the runtime and launcher under temporary names, then publishes them with renames. A failed copy cleans only its own staging paths. No sudoers file, passwordless sudo rule, sudo default, Windows setting, package, system service, or unrelated project is changed. Existing install paths cause an abort; the installer will not overwrite them.

## What the runner does

1. Reuses the OS-Ken controller if port 6653 already listens. Otherwise, it starts the controller as the ordinary `harikrishna` user.
2. Reads OVS state and checks for Mininet processes. If Mininet is active or bridge `s1` already exists, it records the observed bridge state and stops without clearing or reusing it.
3. If the state is clear, starts the project's four-host Mininet topology, configures QoS on `s1-eth4`, and runs `pingAll`.
4. Starts h4 monitoring and all three agents; checks switch protocol/target, flows and counters, HTB queues, and host-to-server pings.
5. Stops only h1's identified monitoring-agent PID, waits for NODE DOWN, restarts h1, and waits for RECOVERED.
6. Runs the existing concurrent UDP iperf3 test (15 Mbps offered per flow, 15 seconds), captures `tc -s` counters before and after, and records receiver throughput, jitter, loss, and a separately timed HTB counter estimate.
7. Writes a timestamped transcript under `results/` and updates the latest-run section of `FINAL_VERIFICATION_REPORT.md`.
8. Leaves the Mininet CLI open for the demonstration. Typing `exit` runs Mininet's normal `net.stop()` cleanup.

The runner refuses to execute `mn -c`, delete a bridge, reset OVS, stop the OVS service, or kill unrecognized processes. A detected existing `s1` needs operator review and a separate cleanup decision. For failure recovery it matches the h1 agent's root-owned runtime path, node and port arguments, and network namespace to Mininet's h1 before signaling that PID.

If a Python exception, ordinary test failure, or Ctrl+C occurs after Mininet starts, the runner's `finally` path calls `net.stop()`, checks whether `s1` remains, and records cleanup PASS or FAIL. If cleanup itself fails, it leaves the remaining state for inspection rather than deleting additional OVS objects. When Mininet removes its bridge, the attached QoS is no longer active; unreferenced tagged OVSDB rows may persist and are safely considered on the next setup. The runner never stops the controller or OVS service. On an early stop, unrun stages are marked SKIP; errors are FAIL; warnings remain WARN. The report outcome is BLOCKED, INCOMPLETE, NEEDS ATTENTION, PASS WITH WARNINGS, or PASS as applicable. A forced kill of the runner, WSL shutdown, or power loss bypasses Python cleanup; a later run detects and refuses an existing `s1` rather than resetting it.

## Privilege boundary

The launcher itself is root-owned and accepts no command arguments. The installer rejects a noncanonical project root, symbolic-link source files, and files resolving outside the project directory. Project Python files are copied into a root-owned snapshot. The launcher starts Python with an empty environment and isolated mode, so `PYTHONPATH`, user site packages, and the writable project directory cannot override root imports. The root runner imports scripts only from its root-owned snapshot. The controller runs as `harikrishna`, not root.

The only privileged command needed from the user is the one interactive installer invocation. No sudoers file or reusable passwordless privilege is installed.

The runner performs project-scoped OVS/Mininet setup, attaches new QoS only to `s1-eth4`, and removes only unused QoS rows tagged for this project; it preserves QoS shared with or attached to another port. Root-generated logs are created with exclusive temporary-file creation, then published into the workspace by a helper process running as the regular user. It does not install software.

The controller is started or reused as the regular `harikrishna` user and does not require root. Root is needed for Mininet namespace/veth creation, OVSDB control in this WSL setup, `mnexec` namespace probes, and HTB/`tc` inspection. The helper needs root only while the single full verification is active; it does not change service enablement or access-control policy.

## Exact review files

Review [install_cn11_launcher.sh](</home/harikrishna/cn-demo/Team1_Project11_Remote_System_Health_Monitoring/install_cn11_launcher.sh>) and [CN11_Demo_Runner.py](</home/harikrishna/cn-demo/Team1_Project11_Remote_System_Health_Monitoring/CN11_Demo_Runner.py>) before authorizing the install. The generated root-owned wrapper contents are:

```sh
#!/bin/sh
set -eu
if [ "$#" -ne 0 ]; then
    echo 'This fixed-scope launcher accepts no arguments.' >&2
    exit 64
fi
exec /usr/bin/env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin HOME=/root LANG=C.UTF-8 /usr/bin/python3 -I /opt/cn-project11/CN11_Demo_Runner.py
```

## Run after review

From an interactive Ubuntu WSL terminal:

```bash
cd /home/harikrishna/cn-demo/Team1_Project11_Remote_System_Health_Monitoring
sudo bash ./install_cn11_launcher.sh
```

Enter the password only at Ubuntu's sudo prompt. The installer runs the workflow immediately. If it reports an existing `s1`, it safely stops and records that state rather than cleaning it up.
