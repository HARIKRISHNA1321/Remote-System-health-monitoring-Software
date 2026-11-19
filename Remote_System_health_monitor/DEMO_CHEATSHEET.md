# Project 11 demo cheatsheet

Project: Remote System Health Monitoring Using SDN

## Startup

Open three Ubuntu WSL terminals. In each, use the project directory:

```bash
cd /home/harikrishna/cn-demo/Team1_Project11_Remote_System_Health_Monitoring
```

### One-command automated run (after launcher installation)

In an interactive Ubuntu WSL terminal, run:

```bash
sudo /usr/local/sbin/cn11-demo
```

The fixed-scope launcher runs connectivity, flow/QoS, monitoring, failure/recovery, and congestion checks, writes a timestamped transcript and updates `FINAL_VERIFICATION_REPORT.md`, then leaves `mininet>` open for the presentation. Type `exit` to stop the topology cleanly. If it reports an existing `s1` bridge, do not run `mn -c`; review the OVS state and get explicit approval before cleaning up that bridge.

**Terminal 1 — OS-Ken controller**

```bash
./start_controller.sh
```

Keep it open. Expected evidence includes OS-Ken startup and a switch connected message after Terminal 2 starts.

**Terminal 2 — Mininet network**

```bash
./start_network.sh
```

Enter the sudo password when prompted. Wait for the connectivity test, monitoring services, and `mininet>` prompt. `pingAll` should report no packet loss.

**Terminal 3 — live verification**

```bash
cd /home/harikrishna/cn-demo/Team1_Project11_Remote_System_Health_Monitoring
sudo python3 CN_Project11_Verifier.py
```

The verifier is read-only except for one-packet ping probes and a short counter observation. For the optional throughput experiment, with Mininet still running:

```bash
sudo python3 CN_Project11_Verifier.py --congestion
```

This sends simultaneous UDP iperf traffic for 15 seconds and stops only the temporary iperf client/server processes it creates. Save output as a newly observed run; don’t substitute historical README results for this run.

## Demonstrations at `mininet>`

**Health reports**

```text
h4 tail -n 25 /tmp/monitor.log
```

Expect NORMAL / QUEUE 0 reports from h2 and h3, CRITICAL / QUEUE 1 reports from h1, sequence numbers, CPU/memory, and latency.

**OpenFlow classification and counters**

```text
sh ovs-ofctl -O OpenFlow13 dump-flows s1
```

Look for UDP destination ports 5005→`set_queue:0`, 5006→`set_queue:1`, 5201→`set_queue:0`, and 5202→`set_queue:1`. The expected output action to h4 is `output:4`. Packet counters should rise while agents run.

**QoS**

```text
sh ovs-vsctl list QoS
sh ovs-vsctl list Queue
sh tc -s class show dev s1-eth4
```

Expected parent HTB rate is 10 Mbps. Queue 0 is configured with a 1 Mbps minimum; Queue 1 with an 8 Mbps minimum. These settings describe configured scheduling and do not guarantee exact application throughput in every run.

**Failure and recovery**

Find h1’s agent process:

```text
h1 pgrep -af agents.py
```

Stop only the PID whose command includes `--node-id 10.0.0.1`:

```text
h1 kill ACTUAL_PID
```

Wait about 8 seconds, then confirm `[NODE DOWN]`:

```text
h4 grep -E 'NODE DOWN|RECOVERED' /tmp/monitor.log
```

Restart h1’s critical agent:

```text
h1 python3 -u /home/harikrishna/cn-demo/Team1_Project11_Remote_System_Health_Monitoring/agents.py --node-id 10.0.0.1 --server-ip 10.0.0.4 --port 5006 > /tmp/h1-recovery.log 2>&1 &
```

Confirm `[RECOVERED] 10.0.0.1` appears in `/tmp/monitor.log` and h1’s 5006 flow counter advances. Do not kill a PID unless its command line identifies h1’s agent.

## Stop cleanly

At `mininet>`, type:

```text
exit
```

This exits the Mininet CLI and runs the topology’s `finally` cleanup. Then press Ctrl+C in Terminal 1 to stop OS-Ken. Avoid `mn -c` during a live network; it is a cleanup command that can tear down Mininet state.

## Viva quick answers

- **Why UDP?** Reports are small, periodic telemetry datagrams; the sender avoids connection setup and the receiver uses sequence numbers and timeouts to expose loss or silence. UDP itself does not guarantee delivery.
- **What does Mininet do?** It creates isolated virtual hosts, links, and an OVS switch so the network can be exercised on one Linux machine.
- **What does the controller do?** OS-Ken speaks OpenFlow 1.3 to OVS, learns source MAC locations, and installs forwarding and UDP queue-selection rules.
- **How does QoS work here?** OpenFlow `set_queue` selects queue 0 or 1 on the h4 output port. OVS attaches Linux HTB with a 10 Mbps parent and configured queue rates/priorities.
- **Does monitoring dynamically change priority?** No. h1 is configured as critical by using UDP 5006; CPU/memory alerts are displayed but do not change OpenFlow policy.
- **How is failure detected?** The monitor tracks last-seen times and declares a node down after the configured six-second timeout. A subsequent valid report emits recovery.
- **What does iperf prove?** It measures observed transport performance during a particular run. Compare receiver summaries and HTB counters, noting measurement interval and observation point; don’t claim configured minimum rates are guaranteed delivered rates.

## Final checklist

- [ ] Controller listens on 6653 and reports switch connected.
- [ ] `s1` exists with four interfaces and OpenFlow 1.3.
- [ ] `pingAll` succeeds.
- [ ] h4 monitor and h1/h2/h3 agents run; reports are recent.
- [ ] Four UDP flow rules select the intended queue and counters advance.
- [ ] QoS is attached to `s1-eth4`; parent and queue settings match configuration.
- [ ] Optional congestion run completes and its raw output is retained.
- [ ] Failure and recovery are demonstrated only if time permits.
- [ ] Network exits with `exit`; controller is stopped with Ctrl+C.
