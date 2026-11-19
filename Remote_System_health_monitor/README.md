# Team 1 – Project 11
# Remote System Health Monitoring using SDN

## 1. Project Overview

This project implements a networked application for monitoring the
health of multiple hosts using UDP socket programming and Software
Defined Networking (SDN).

Three monitoring agents (h1, h2 and h3) periodically collect system
statistics and send reports to a central monitoring server running
on h4.

An OS-Ken SDN controller manages the Open vSwitch switch using
OpenFlow 1.3.

The network also implements traffic classification and prioritisation
using Open vSwitch QoS and Linux HTB queues.

## 2. Network Architecture

The Mininet topology contains:

- h1: Critical monitoring traffic
- h2: Normal monitoring traffic
- h3: Normal monitoring traffic
- h4: Central monitoring server
- s1: Open vSwitch
- c0: Remote OS-Ken controller

IP addresses:

| Host | IP address |
|------|------------|
| h1 | 10.0.0.1 |
| h2 | 10.0.0.2 |
| h3 | 10.0.0.3 |
| h4 | 10.0.0.4 |

The controller listens on 127.0.0.1:6653.

## 3. Project Files

| File | Description |
|------|-------------|
| agents.py | Collects and sends host health reports |
| monitor.py | Receives reports and detects node failures |
| controller.py | OS-Ken SDN controller and OpenFlow rules |
| topology.py | Creates Mininet topology and configures QoS |
| start_controller.sh | Launches the SDN controller |
| start_network.sh | Launches the complete Mininet application |
| requirements.txt | Python dependencies |
| PROJECT_REPORT.pdf | Final project report with code and command explanations |
| results/ | Saved performance and verification logs |

## 4. Technologies Used

- Python
- UDP socket programming
- Mininet 2.3.0
- Open vSwitch 3.7.1
- OS-Ken 3.1.1
- OpenFlow 1.3
- Linux HTB QoS
- psutil
- iperf3

Tested environment:

- Ubuntu 26.04 LTS on WSL 2
- Python 3.14.4
- OS-Ken 3.1.1
- psutil 7.2.2 in the virtual environment
- psutil 7.1.0 in Mininet hosts

## 5. Network Communication

The agents send UDP health reports to h4.

Each report contains:

- Node ID
- Sequence number
- Timestamp
- CPU usage
- Memory usage
- Process count
- Network bytes received
- Network bytes sent

Monitoring ports:

| UDP port | Traffic type |
|-----------|--------------|
| 5005 | Normal monitoring reports |
| 5006 | Critical monitoring reports |

The monitoring server listens on both ports.

The current configuration assigns h1 to critical traffic and h2/h3
to normal traffic.

## 6. Failure Detection and Recovery

The monitoring server maintains the last report received from each
node.

The configured timeout is 6 seconds.

When a node stops sending reports for longer than the timeout,
the server displays a NODE DOWN message.

When reports resume, the server displays RECOVERED.

This functionality was tested by stopping and restarting h1's
monitoring agent.

Observed output:

[NODE DOWN] 10.0.0.1 has not reported for 6.2 seconds
[RECOVERED] 10.0.0.1

## 7. SDN and OpenFlow Implementation

The controller uses OpenFlow 1.3.

It provides MAC address learning and installs forwarding rules.

It also classifies UDP traffic using destination ports.

| UDP destination | Queue | Purpose |
|-----------------|-------|---------|
| 5005 | 0 | Normal health reports |
| 5006 | 1 | Critical health reports |
| 5201 | 0 | Normal performance tests |
| 5202 | 1 | Critical performance tests |

The performance-test rules are installed automatically by the
controller, although iperf3 servers are started separately.

## 8. QoS Configuration

QoS is attached to switch port s1-eth4, which connects to h4.

The parent HTB rate is configured as 10 Mbps.

| Parameter | Queue 0 | Queue 1 |
|-----------|---------|---------|
| Traffic | Normal | Critical |
| Minimum rate | 1 Mbps | 8 Mbps |
| Maximum rate | 10 Mbps | 10 Mbps |
| HTB priority | 7 | 0 |

The topology automatically creates and attaches the QoS configuration
when it starts.

The OpenFlow set_queue action selects the queue for each matching
packet.

## 9. Installation Requirements

Install the system packages:

sudo apt update

sudo apt install -y mininet openvswitch-switch python3-psutil \
python3-venv python3-pip iperf3

Load the Open vSwitch kernel module if required:

sudo modprobe openvswitch

Start Open vSwitch:

sudo service openvswitch-switch start

Create and activate a virtual environment:

cd ~/cn-project-11

python3 -m venv .venv

source .venv/bin/activate

Install Python dependencies:

python -m pip install --upgrade pip

pip install -r requirements.txt

The system Python package python3-psutil is required because
Mininet hosts use the system Python interpreter.

## 10. Running the Project

Use two Ubuntu terminals.

### Terminal 1 – Start the SDN Controller

cd ~/cn-project-11

./start_controller.sh

Keep this terminal running.

### Terminal 2 – Start the Network

cd ~/cn-project-11

./start_network.sh

Enter the sudo password when requested.

The topology script automatically:

1. Creates h1, h2, h3 and h4.
2. Creates switch s1.
3. Connects to the remote SDN controller.
4. Configures HTB QoS.
5. Tests host connectivity.
6. Starts the monitoring server on h4.
7. Starts all three monitoring agents.
8. Opens the Mininet CLI.

No manual agent startup is required.

## 11. Useful Verification Commands

Run these at the Mininet prompt.

Check the monitoring server:

h4 pgrep -af monitor.py

Check the monitoring agents:

h1 pgrep -af agents.py

View monitoring reports:

h4 tail -n 30 /tmp/monitor.log

View OpenFlow rules:

sh ovs-ofctl -O OpenFlow13 dump-flows s1

View HTB statistics:

sh tc -s class show dev s1-eth4

View QoS configuration:

sh ovs-vsctl list QoS

## 12. Failure Detection Demonstration

The following steps demonstrate node failure detection and recovery.

At the Mininet prompt, find the h1 agent process:

```bash
h1 pgrep -af agents.py
```

Identify the process whose command contains `--node-id 10.0.0.1`.
Stop that process using its actual process ID:

```bash
h1 kill ACTUAL_PID
```

Replace `ACTUAL_PID` with the process ID shown above. Wait for the
monitoring timeout:

```bash
sh sleep 8
```

Check the monitoring server:

```bash
h4 grep -E 'NODE DOWN|RECOVERED' /tmp/monitor.log
```

Restart h1 as a critical agent. The Mininet hosts inherit the project
working directory used to launch the topology, so the relative path
avoids a machine-specific username:

```bash
h1 python3 -u ./agents.py \
  --node-id 10.0.0.1 \
  --server-ip 10.0.0.4 \
  --port 5006 \
  > /tmp/h1-recovery.log 2>&1 &
```

The monitoring server should display `RECOVERED` after receiving
new health reports from h1.

## 13. Performance Evaluation

iperf3 was used to generate UDP traffic inside the Mininet topology.
The controller maps UDP destination port 5201 to Queue 0 (normal)
and port 5202 to Queue 1 (critical).

### Earlier congestion runs

An earlier differentiated-queue run and a reference run with both
flows assigned to Queue 0 produced the following receiver results.
These are separate observed runs, not a claim of a perfectly
controlled one-variable comparison.

| Scenario | Normal received | Critical received | Normal jitter | Critical jitter |
|----------|------------------|-------------------|---------------|-----------------|
| Differentiated queues | 4.13 Mbps | 8.00 Mbps | 7.909 ms | 0.015 ms |
| Both flows in Queue 0 | 6.42 Mbps | 7.30 Mbps | 5.236 ms | 1.369 ms |

Packet loss reported by the receiver was 0% in both runs.

### Individual queue rate-limit tests

Each queue was tested separately with an offered UDP rate of 15 Mbps
for 15 seconds.

| Metric | Queue 0 - Normal | Queue 1 - Critical |
|--------|------------------|--------------------|
| Offered bitrate | 15 Mbps | 15 Mbps |
| Received bitrate | 9.72 Mbps | 9.71 Mbps |
| Jitter | 1.364 ms | 1.816 ms |
| Packet loss | 0% | 0% |

Both individual tests received approximately 10 Mbps, consistent
with their configured 10 Mbps maximum rate.

### Latest simultaneous congestion experiment

Both sources offered 15 Mbps simultaneously for 60 seconds.

| Metric | Normal - Queue 0 | Critical - Queue 1 |
|--------|------------------|--------------------|
| Offered bitrate | 15 Mbps | 15 Mbps |
| Received bitrate | 1.71 Mbps | 8.81 Mbps |
| Jitter | 13.721 ms | 1.509 ms |
| Packet loss | 0% | 0% |

Critical traffic achieved approximately 5.15 times the receiver
throughput of normal traffic in this run.

### Live HTB bandwidth-counter sample

During the simultaneous experiment, HTB class counters were sampled
for 30.12 seconds while both streams were active.

| HTB class | Measured rate |
|------------|---------------|
| Queue 0 - Normal | 1.00 Mbps |
| Queue 1 - Critical | 9.00 Mbps |
| Parent class | 10.00 Mbps |

The live counter sample shows the parent class at its configured
10 Mbps rate during that sampling interval. The complete 60-second
iperf receiver averages sum to 10.52 Mbps. The sample covers only
part of the iperf run and uses a different observation point, so
these measurements should not be treated as directly identical.
The result supports differentiated prioritisation, while a fully
aligned end-to-end aggregate-rate measurement would strengthen the
strict parent-cap validation.

### Evaluation summary

The saved experiments demonstrate that:

- OpenFlow rules classify normal and critical UDP traffic into
  separate output queues.
- Each queue individually reached approximately 10 Mbps when
  offered 15 Mbps.
- Under simultaneous high demand, critical traffic received
  substantially higher throughput and lower jitter.
- A live HTB counter sample recorded 1 Mbps on Queue 0,
  9 Mbps on Queue 1 and 10 Mbps at the parent.
- The selected iperf receiver summaries reported 0% packet loss.

These are observed results from the tested WSL 2 and Mininet
installation. Performance may vary with host load and timing.

## 14. Saved Results

The `results/` directory includes monitoring output, OpenFlow and
QoS evidence, and iperf3 logs. Key files include:

- `auto_start_monitor.log` and `fresh_start_monitor.log`
- `auto_start_flows.txt` and `fresh_start_flows.txt`
- `auto_start_qos.txt`, `auto_start_qos_config.txt`,
  `fresh_start_qos.txt` and `fresh_start_qos_config.txt`
- `baseline-normal.log` and `baseline-critical.log`
- `normal-congestion-client.log` and `critical-congestion-client.log`
- `queue0-cap-test.log` and `queue1-cap-test.log`
- `simultaneous-normal-15m.log` and `simultaneous-critical-15m.log`
- `final-normal.log` and `final-critical.log`
- `shared_bandwidth_verification.txt`

The ZIP handoff also contains the final project report PDF and a
package manifest.

## 15. Current Limitations and Scope

1. Traffic priority is assigned using UDP destination ports. CPU or
   memory alerts do not automatically change a host's network
   priority.

2. The controller installs fixed queue-classification rules at
   switch connection time. MAC learning is dynamic, but traffic
   priority is not adaptively changed based on monitoring data.

3. The health-report application uses UDP. The project does not
   implement an authenticated or encrypted reporting protocol.

4. The shared 10 Mbps parent rate was observed in a 30.12-second
   live HTB counter sample. The full iperf receiver averages differ
   slightly; a precisely aligned aggregate-rate test would improve
   validation.

5. The performance-testing iperf3 servers are started manually;
   topology.py automatically starts only the monitoring server
   and the three health agents.

6. The project was tested in the documented WSL 2 environment.
   Teammate-laptop reproduction remains to be confirmed.

## 16. Stopping the Project

At the Mininet prompt, type:

exit

This stops the network and its host processes.

Then stop the controller in Terminal 1 using Ctrl+C.

## 17. Important Notes

- Start the controller before starting the Mininet topology.
- Keep the controller terminal open during the demonstration.
- Do not copy the .venv directory to another laptop.
- Create a new virtual environment on the teammate's laptop.
- Install system dependencies before running the project.
- Use the launch scripts for the normal demonstration.

