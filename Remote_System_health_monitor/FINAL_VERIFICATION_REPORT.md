# Project 11 verification report

**Report state:** In progress. Controller was started; full topology and functional checks remain gated on the interactive Linux sudo context.

## Current evidence

| Feature | Status | Evidence |
|---|---|---|
| WSL2 Ubuntu | PASS | `wsl --list --verbose` succeeded with sandbox escalation and showed Ubuntu Running, Version 2. |
| Open vSwitch daemons | PASS | Read-only WSL process check found `ovsdb-server` and `ovs-vswitchd`; service state was `active`. |
| Controller / TCP 6653 | PASS | Started via `./start_controller.sh` in a managed foreground session. Port 6653 accepted a local connection. OS-Ken logged `Switch connected: 1` and OpenFlow switch-features negotiation. |
| Mininet / topology process | NOT RUNNING / NEEDS CHECK | No `mnexec`, `topology.py`, or `monitor.py` process was visible. However, OS-Ken received a switch connection (datapath ID 1), so an OVS bridge is present. Inspect `ovs-vsctl show` and current QoS before launching topology, since topology startup replaces QoS attached to `s1-eth4`. |
| OVS bridge, flows, QoS | PARTIALLY OBSERVED | A switch connected to OS-Ken over OpenFlow, but bridge details, exact rules, counters, and queue configuration require privileged OVS queries unavailable to the noninteractive execution context. |
| Monitoring server / agents | NOT RUNNING | No `monitor.py` or `agents.py` process was found. |
| Recent reports | NOT AVAILABLE | `/tmp/monitor.log` and `/tmp/h1-recovery.log` were absent at the latest check. |
| Source syntax / runtime verification | PARTIAL PASS | AST syntax parsing passed for agents.py, monitor.py, controller.py, topology.py, and the corrected verifier. Full verifier run is pending. |

Controller startup emitted OS-Ken's Eventlet deprecation/RLock warning, then continued loading the application, bound the controller socket, negotiated with the connected switch, and logged all four queue mappings. Treat the warning as a future-maintenance note; it did not prevent the controller from starting in this run.

## Source review and correction

The architecture in the source is four Mininet hosts and one OVS switch. h1 sends critical UDP reports to port 5006; h2 and h3 use normal port 5005. h4 listens on both. The OS-Ken controller negotiates OpenFlow 1.3, learns MAC addresses, forwards to the learned output (or floods unknown destinations), and installs fixed rules selecting queue 0 or 1 for UDP ports 5005, 5006, 5201, and 5202. `topology.py` configures Linux HTB on `s1-eth4` with a 10 Mbps parent, Queue 0 minimum 1 Mbps and Queue 1 minimum 8 Mbps.

Fixed one verifier issue: `CN_Project11_Verifier.py` required the literal interface name `s1-eth4` in flow output actions. The topology’s correct OpenFlow action is numeric `output:4`. The verifier now accepts numeric port 4 or an interface-name representation while still requiring the expected queue. A timestamped pre-change backup, `CN_Project11_Verifier.py.bak-*`, is in the project directory. The updated verifier has not yet been run against a live switch.

## Historical results (not a current run)

The README and saved `verification_results.txt` describe earlier tests. The latter recorded 33 PASS, 3 WARN and 4 parser-related FAIL, with h1 intentionally stopped and recovery pending at that capture. The README reports historical simultaneous traffic of 1.71 Mbps normal and 8.81 Mbps critical, with 13.721 ms vs 1.509 ms jitter, and a separate 30.12-second HTB counter sample of 1 and 9 Mbps (10 Mbps parent). These are saved prior observations; they are not results from today’s live run.

## Remaining work

1. In the user's Ubuntu terminal, inspect the existing switch (`sudo ovs-vsctl show`, `sudo ovs-vsctl list QoS`, `sudo ovs-ofctl -O OpenFlow13 dump-flows s1`) before topology startup. The controller's switch-features log indicates a connected switch is already present.
2. After confirming this is the project bridge and the state is safe to replace, run `sudo python3 /home/harikrishna/cn-demo/Team1_Project11_Remote_System_Health_Monitoring/topology.py` in an interactive terminal; verify `pingAll` and that monitor/agents start.
3. Run the corrected quick verifier from a third terminal; inspect flows, queue configuration, recent reports, recovery state, and counters.
4. If the quick verification passes, run the optional simultaneous iperf3 test, retaining its actual output and comparing it with contemporaneous HTB counters.
5. Record exact live outcomes and any remaining warnings here before the demonstration.

The OS-Ken controller was started as explicitly authorized. No service or network configuration was changed by the diagnostics. The verifier parser correction and later topology QoS-scope correction are documented below; the topology edit has a timestamped backup. For repeatable commands and expected evidence, see `DEMO_CHEATSHEET.md`.

## Automation preparation update — 2026-11-18

The controller was rechecked: port 6653 remained listening and the OS-Ken process was present. Mininet, Open vSwitch, and iperf3 executables are available. The controller log shows an OpenFlow switch-features handshake and `Switch connected: 1`. No topology, monitoring server, or agent process was present in the process listing; `/tmp/monitor.log` was absent.

Prepared `CN11_Demo_Runner.py`, `install_cn11_launcher.sh`, and `CN11_LAUNCHER_REVIEW.md`. Syntax checks passed for the runner, verifier, and installer. The runner is designed to refuse an existing `s1` bridge rather than deleting or reusing it, and to run the full test sequence only when OVS/Mininet state is clear. It records PASS/FAIL/WARN/SKIP rows, a transcript, and a latest-run section. It does not stop the controller. The privileged installer has **not** been executed, so no root-owned files were installed and no live functional tests from that runner have occurred.

During the final safety review, `topology.py` was tightened so QoS cleanup is limited to this project's unattached tagged records and the QoS attached to `s1-eth4` when it is not shared with another OVS port. Queue rows referenced by other QoS records are preserved. The pre-edit file is backed up as `topology.py.bak-safety-*`.

The runner was also hardened before any privileged execution: installer sources must be regular non-symlink files resolving under the canonical project directory; the installed wrapper clears the environment and starts Python isolated from user import paths; report writes are published as the regular user; root temporary files use exclusive creation; h1 signaling is constrained to the expected runtime script and h1 network namespace; existing OVS bridges are checked via `ovs-vsctl list-br` and never cleared; interruption/error paths report unrun stages as SKIP and call Mininet cleanup. No installer or privileged runner has been executed.

Final static safety checks passed for all six project Python files, installer shell syntax, a synthetic HTB counter sample, and isolated system Python imports of Mininet/psutil. These checks do not replace live OVS/Mininet tests. The root runner does not stop OS-Ken or Open vSwitch. Ordinary exceptions and Ctrl+C run Mininet cleanup and verify whether `s1` remains; forced termination or WSL shutdown can bypass cleanup, in which case the next run refuses to reset the bridge. Report publication occurs as `harikrishna`; if it fails, the launcher exits nonzero and prints the report-write error.
