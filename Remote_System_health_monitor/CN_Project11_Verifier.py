#!/usr/bin/env python3
"""Project 11: safe WSL2/Mininet/OS-Ken verification.

Default: inspection, small ICMP probes and flow-counter observation only.
Optional --congestion: short concurrent UDP iperf3 throughput test.
Never stops/restarts Mininet, the SDN controller, or health agents.

Run from the project directory: sudo python3 CN_Project11_Verifier.py
"""

import argparse
import ast
import collections
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time

PROJECT = Path(__file__).resolve().parent
LABELS = {"h1": "10.0.0.1", "h2": "10.0.0.2", "h3": "10.0.0.3", "h4": "10.0.0.4"}
AGENT_PORTS = {"h1": 5006, "h2": 5005, "h3": 5005}
FLOW_QUEUES = {5005: 0, 5006: 1, 5201: 0, 5202: 1}
RESULTS = []


def record(kind, name, details=""):
    RESULTS.append((kind, name, details))
    mark = {"PASS": "+", "FAIL": "!", "WARN": "?", "SKIP": "-"}[kind]
    print(f"[{mark}] {kind:<4}  {name}" + (f" — {details}" if details else ""), flush=True)


def cmd(argv, timeout=5):
    try:
        p = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as ex:
        return 127, "", str(ex)


def proc_table():
    out = []
    for ent in Path('/proc').iterdir():
        if not ent.name.isdecimal():
            continue
        try:
            args = (ent / 'cmdline').read_bytes().replace(b'\0', b' ').decode('utf-8', 'replace').strip()
            stat = (ent / 'stat').read_text(errors='replace')
            state = stat[stat.rfind(')') + 2:][:1]
            if args and state != 'Z':
                out.append((int(ent.name), args))
        except (OSError, ValueError):
            pass
    return out


def matches_script(args, filename):
    words = args.split()
    return any(Path(word).name == filename for word in words)


def find_procs(processes, filename):
    return [(pid, args) for pid, args in processes if matches_script(args, filename)]


def get_host_pid(processes, host, agents, monitors):
    # Mininet host shells normally appear as "mininet:h1", etc.
    for pid, args in processes:
        if re.search(r'(^|\s)mininet:' + re.escape(host) + r'(\s|$)', args):
            return pid
    if host == 'h4':
        return monitors[0][0] if monitors else None
    for pid, args in agents:
        if re.search(r'--node-id\s+' + re.escape(LABELS[host]) + r'(\s|$)', args):
            return pid
    return None


def find_agent(agents, host):
    expected = LABELS[host]
    port = AGENT_PORTS[host]
    for pid, args in agents:
        if re.search(r'--node-id\s+' + re.escape(expected) + r'(\s|$)', args) and re.search(r'--port\s+' + str(port) + r'(\s|$)', args):
            return pid
    return None


def parse_flow_stats(text):
    flows = {}
    for line in text.splitlines():
        if 'udp' not in line or 'nw_dst=10.0.0.4' not in line:
            continue
        m = re.search(r'tp_dst=(\d+)\b', line)
        if not m:
            continue
        port = int(m.group(1))
        npackets = re.search(r'n_packets=(\d+)', line)
        queue = re.search(r'set_queue:(\d+)', line)
        flows[port] = {
            'packets': int(npackets.group(1)) if npackets else None,
            'queue': int(queue.group(1)) if queue else None,
            'line': line.strip(),
        }
    return flows


def get_flows():
    return cmd(['ovs-ofctl', '-O', 'OpenFlow13', 'dump-flows', 's1'], timeout=8)


def ovs_get(table, row, column):
    return cmd(['ovs-vsctl', 'get', table, row, column])


def inspect_project():
    print('\n=== 1. Project and dependencies ===')
    scripts = ['agents.py', 'monitor.py', 'controller.py', 'topology.py']
    missing = [x for x in scripts + ['start_controller.sh', 'start_network.sh', 'requirements.txt'] if not (PROJECT / x).is_file()]
    record('FAIL' if missing else 'PASS', 'Project source files', ', '.join(missing) if missing else str(PROJECT))
    for name in scripts:
        if (PROJECT / name).is_file():
            try:
                ast.parse((PROJECT / name).read_text(encoding='utf-8'), filename=name)
            except (SyntaxError, UnicodeError) as ex:
                record('FAIL', name + ' syntax', str(ex))
            else:
                record('PASS', name + ' syntax')
    tools = ['mn', 'mnexec', 'ovs-vsctl', 'ovs-ofctl', 'tc', 'iperf3']
    missing_tools = [name for name in tools if not shutil.which(name)]
    record('WARN' if missing_tools else 'PASS', 'System tools', 'Missing: ' + ', '.join(missing_tools) if missing_tools else ', '.join(tools))
    if (PROJECT / '.venv/bin/python').exists():
        rc, out, err = cmd([str(PROJECT / '.venv/bin/python'), '-c', 'import os_ken; print("OS-Ken import OK")'], timeout=6)
        record('PASS' if rc == 0 else 'FAIL', 'OS-Ken virtual environment', out if rc == 0 else err[-220:])
    else:
        record('FAIL', 'OS-Ken virtual environment', '.venv/bin/python not found in project folder')
    rc, out, err = cmd(['python3', '-c', 'import psutil; print(psutil.__version__)'])
    record('PASS' if rc == 0 else 'WARN', 'System Python psutil', out if rc == 0 else err[-180:])


def inspect_sdn():
    print('\n=== 2. SDN controller / topology ===')
    try:
        with socket.create_connection(('127.0.0.1', 6653), timeout=1.5):
            record('PASS', 'Controller TCP 127.0.0.1:6653', 'Accepting connections')
    except OSError as ex:
        record('FAIL', 'Controller TCP 127.0.0.1:6653', str(ex))
    rc, out, err = cmd(['ovs-vsctl', 'show'])
    record('PASS' if rc == 0 else 'FAIL', 'Open vSwitch service', 'Responding' if rc == 0 else err[-200:])
    rc, out, err = cmd(['ovs-vsctl', 'br-exists', 's1'])
    record('PASS' if rc == 0 else 'FAIL', 'Mininet switch s1', 'Bridge exists' if rc == 0 else 'Switch not present')
    if rc != 0:
        return False
    rc, out, err = cmd(['ovs-vsctl', 'list-ports', 's1'])
    ports = set(out.splitlines())
    expected = {f's1-eth{i}' for i in range(1, 5)}
    record('PASS' if rc == 0 and expected.issubset(ports) else 'FAIL', 'Four switch interfaces', ', '.join(sorted(ports)) if rc == 0 else err[-200:])
    rc, out, err = ovs_get('Bridge', 's1', 'protocols')
    record('PASS' if rc == 0 and 'OpenFlow13' in out else 'WARN', 'OpenFlow 1.3', out if rc == 0 else err[-180:])
    rc, out, err = cmd(['ovs-vsctl', 'get-controller', 's1'])
    record('PASS' if rc == 0 and '6653' in out else 'WARN', 'Switch controller target', out if rc == 0 else err[-180:])
    return True


def inspect_qos(switch_ready):
    print('\n=== 3. QoS and OpenFlow classification ===')
    if not switch_ready:
        record('SKIP', 'QoS / flow checks', 'Bridge s1 is not running')
        return {}
    rc, uuid, err = ovs_get('Port', 's1-eth4', 'qos')
    uuid = uuid.strip().strip('"')
    if rc != 0 or not re.fullmatch(r'[\da-fA-F-]{36}', uuid):
        record('FAIL', 'QoS attachment on s1-eth4', err[-200:] if rc != 0 else f'Value: {uuid}')
    else:
        record('PASS', 'QoS attachment on s1-eth4', uuid)
        rc, typ, err = ovs_get('QoS', uuid, 'type')
        record('PASS' if rc == 0 and 'linux-htb' in typ else 'WARN', 'QoS discipline', typ if rc == 0 else err[-180:])
        rc, props, err = ovs_get('QoS', uuid, 'other_config')
        record('PASS' if rc == 0 and re.search(r'max-rate="?10000000"?', props) else 'WARN', 'Parent 10 Mbps limit', props if rc == 0 else err[-180:])
        rc, queues, err = ovs_get('QoS', uuid, 'queues')
        matches = dict((int(a), b) for a, b in re.findall(r'([01])=([\da-fA-F-]{36})', queues))
        record('PASS' if rc == 0 and 0 in matches and 1 in matches else 'FAIL', 'Queue 0 / Queue 1 attached', queues if rc == 0 else err[-180:])
        for idx, expected_min in [(0, '1000000'), (1, '8000000')]:
            if idx not in matches:
                continue
            rc, conf, err = ovs_get('Queue', matches[idx], 'other_config')
            correct = rc == 0 and re.search(r'min-rate="?' + expected_min + r'"?', conf) is not None
            record('PASS' if correct else 'WARN', f'Queue {idx} configured minimum', conf if rc == 0 else err[-180:])
    rc, tc_text, err = cmd(['tc', '-s', 'class', 'show', 'dev', 's1-eth4'])
    record('PASS' if rc == 0 and 'htb' in tc_text else 'WARN', 'Linux HTB classes on s1-eth4', f'{len(tc_text.splitlines())} lines' if rc == 0 else err[-180:])
    rc, flow_text, err = get_flows()
    if rc != 0:
        record('FAIL', 'OpenFlow rule retrieval', err[-220:])
        return {}
    flows = parse_flow_stats(flow_text)
    for port, queue in FLOW_QUEUES.items():
        got = flows.get(port)
        # OpenFlow dumps normally show the numeric output port, not the
        # Linux interface name. Port 4 is h4 on this fixed topology.
        output_to_h4 = got is not None and re.search(
            r'\boutput:(?:4\b|"?s1-eth4"?(?=\s|,|$))', got['line']
        ) is not None
        good = got is not None and got['queue'] == queue and output_to_h4
        record('PASS' if good else 'FAIL', f'UDP {port} -> Queue {queue} -> h4', f"{got['packets']} packets" if good else (got['line'] if got else 'Rule missing'))
    return flows


def inspect_monitoring(processes):
    print('\n=== 4. Live health monitoring ===')
    monitors = find_procs(processes, 'monitor.py')
    agents = find_procs(processes, 'agents.py')
    record('PASS' if monitors else 'FAIL', 'Monitoring server process', ', '.join(str(p) for p, _ in monitors) if monitors else 'monitor.py not running')
    active = {}
    for host in ('h1', 'h2', 'h3'):
        pid = find_agent(agents, host)
        active[host] = pid
        record('PASS' if pid else 'WARN', host + ' monitoring agent', f'PID {pid}' if pid else f'No agent for {LABELS[host]}:{AGENT_PORTS[host]} (may be intentionally stopped)')
    logfile = Path('/tmp/monitor.log')
    if not logfile.exists():
        record('FAIL', 'Monitoring log', '/tmp/monitor.log not found')
        return active, monitors
    try:
        data = logfile.read_bytes()[-150000:].decode('utf-8', 'replace')
        age = time.time() - logfile.stat().st_mtime
    except OSError as ex:
        record('FAIL', 'Monitoring log', str(ex))
        return active, monitors
    record('PASS' if age < 8 else 'WARN', 'Recent incoming UDP reports', f'Log modified {age:.1f} seconds ago')
    reports = re.findall(r'\[(?:CRITICAL|NORMAL) / QUEUE [01]\] \[(10\.0\.0\.[123])\] Sequence: (\d+)', data)
    latest = {}
    for ip, seq in reports:
        latest[ip] = int(seq)
    for host in ('h1', 'h2', 'h3'):
        ip = LABELS[host]
        record('PASS' if ip in latest else 'WARN', f'{host} reported to h4', f'Latest logged sequence #{latest[ip]} (may be historical)' if ip in latest else 'No entry found in recent log tail')
    down = re.findall(r'\[NODE DOWN\]\s+10\.0\.0\.1[^\n]*', data)
    recovered = re.findall(r'\[RECOVERED\]\s+10\.0\.0\.1', data)
    record('PASS' if down else 'WARN', 'Recorded h1 failure event', down[-1] if down else 'No failure event in examined log tail')
    record('PASS' if recovered else 'WARN', 'Recorded h1 recovery event', recovered[-1] if recovered else 'Not observed yet; restart h1 agent at mininet>')
    return active, monitors


def inspect_ping(processes, agents, monitors):
    print('\n=== 5. Host-to-server ICMP (small safe probes) ===')
    if not shutil.which('mnexec'):
        record('SKIP', 'Host pings', 'mnexec missing')
        return
    for host in ('h1', 'h2', 'h3'):
        pid = get_host_pid(processes, host, agents, monitors)
        if pid is None:
            record('SKIP', host + ' -> h4', 'Could not locate a PID in this Mininet host namespace')
            continue
        rc, out, err = cmd(['mnexec', '-a', str(pid), 'ping', '-n', '-c', '1', '-W', '2', LABELS['h4']], timeout=5)
        record('PASS' if rc == 0 else 'WARN', host + ' -> h4 ICMP', '1 reply received' if rc == 0 else (err or out)[-210:])


def inspect_flow_progress(before, agents):
    print('\n=== 6. Live OpenFlow packet-counter progress ===')
    if not before:
        record('SKIP', 'Counter progress', 'Baseline OpenFlow counters unavailable')
        return
    time.sleep(3.5)
    rc, out, err = get_flows()
    if rc != 0:
        record('WARN', 'Counter progress', err[-180:])
        return
    after = parse_flow_stats(out)
    for port in (5005, 5006):
        n0 = before.get(port, {}).get('packets')
        n1 = after.get(port, {}).get('packets')
        if n0 is None or n1 is None:
            record('WARN', f'UDP {port} counter', 'Packet count unavailable')
            continue
        delta = n1 - n0
        expected_active = port == 5005 or agents.get('h1') is not None
        kind = 'PASS' if delta > 0 else ('FAIL' if expected_active else 'WARN')
        record(kind, f'UDP {port} packets arriving', f'{n0} -> {n1} (+{delta} in 3.5 seconds)')


def iperf_result(raw):
    try:
        info = json.loads(raw)
        if 'error' in info:
            return None, info['error']
        received = info.get('end', {}).get('sum', {})
        if not received or 'bits_per_second' not in received:
            received = info.get('end', {}).get('sum_received', {})
        if not received or 'bits_per_second' not in received:
            return None, 'Receiver summary missing from iperf3 JSON'
        return {'mbps': received['bits_per_second'] / 1e6,
                'jitter_ms': received.get('jitter_ms'),
                'loss_pct': received.get('lost_percent')}, ''
    except (json.JSONDecodeError, TypeError, ValueError) as ex:
        return None, str(ex)


def run_congestion(processes, agents, monitors):
    print('\n=== 7. Optional 15-second simultaneous congestion test ===')
    if not shutil.which('mnexec') or not shutil.which('iperf3'):
        record('SKIP', 'Congestion test', 'mnexec or iperf3 missing')
        return
    host_pids = {h: get_host_pid(processes, h, agents, monitors) for h in ('h1', 'h2', 'h4')}
    if any(p is None for p in host_pids.values()):
        record('SKIP', 'Congestion test', 'Cannot enter all required Mininet host namespaces')
        return
    for pid, args in processes:
        if re.search(r'\biperf3\b', args) and re.search(r'(^|\s)-s(\s|$)', args) and re.search(r'\b520[12]\b', args):
            record('SKIP', 'Congestion test', f'Existing iperf3 server PID {pid}; will not interfere')
            return

    def inhost(host, argv):
        return ['mnexec', '-a', str(host_pids[host])] + argv

    serverprocs = []
    clients = []
    try:
        for port in (5201, 5202):
            serverprocs.append(subprocess.Popen(inhost('h4', ['iperf3', '-s', '-1', '-p', str(port)]), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True))
        time.sleep(1)
        for host, port in [('h2', 5201), ('h1', 5202)]:
            client = subprocess.Popen(inhost(host, ['iperf3', '-c', LABELS['h4'], '-u', '-p', str(port), '-b', '15M', '-t', '15', '-J']), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            clients.append((host, port, client))
        results = {}
        for host, port, client in clients:
            stdout, stderr = client.communicate(timeout=35)
            if client.returncode != 0:
                record('FAIL', f'iperf3 UDP {host}:{port}', stderr[-250:] or 'Nonzero exit status')
                continue
            metric, msg = iperf_result(stdout)
            if metric is None:
                record('WARN', f'iperf3 UDP {host}:{port}', msg)
                continue
            results[port] = metric
            extra = f"{metric['mbps']:.2f} Mbps received"
            if metric['jitter_ms'] is not None:
                extra += f", jitter {metric['jitter_ms']:.2f} ms"
            if metric['loss_pct'] is not None:
                extra += f", loss {metric['loss_pct']:.1f}%"
            record('PASS', f'{host} -> h4 UDP {port}', extra)
        if 5201 in results and 5202 in results:
            n, c = results[5201]['mbps'], results[5202]['mbps']
            ratio = c / n if n > 0 else float('inf')
            record('PASS' if c > n else 'WARN', 'Critical vs normal throughput', f'critical {c:.2f} Mbps / normal {n:.2f} Mbps, ratio {ratio:.2f}x')
            print('      Note: This is one live test, not a guarantee of identical future results.')
    except (OSError, subprocess.TimeoutExpired) as ex:
        record('FAIL', 'Congestion test execution', str(ex))
    finally:
        for _, _, c in clients:
            if c.poll() is None:
                c.terminate()
                try: c.wait(timeout=2)
                except subprocess.TimeoutExpired: c.kill()
        for s in serverprocs:
            if s.poll() is None:
                s.terminate()
                try: s.wait(timeout=2)
                except subprocess.TimeoutExpired: s.kill()


def main():
    parser = argparse.ArgumentParser(description='Verify Project 11 in running WSL2 Mininet/OVS without changing the running project.')
    parser.add_argument('--congestion', action='store_true', help='ALSO run a short simultaneous 15 Mbps UDP iperf3 QoS test (generates temporary traffic).')
    args = parser.parse_args()
    print('CN PROJECT 11 — AUTOMATIC VERIFICATION')
    print('Date:', dt.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z'))
    print('Project:', PROJECT)
    print('Mode:', 'QUICK + CONGESTION TEST' if args.congestion else 'QUICK / NON-DESTRUCTIVE')
    print('This script does not restart or kill your health agents, controller or Mininet.')
    if os.geteuid() != 0:
        print('\nPlease run using: sudo python3 CN_Project11_Verifier.py')
        return 2
    inspect_project()
    bridge = inspect_sdn()
    before = inspect_qos(bridge)
    processes = proc_table()
    agents, monitors = inspect_monitoring(processes)
    inspect_ping(processes, find_procs(processes, 'agents.py'), monitors)
    inspect_flow_progress(before, agents)
    if args.congestion:
        run_congestion(processes, find_procs(processes, 'agents.py'), monitors)
    print('\n=== Summary ===')
    counts = collections.Counter(kind for kind, _, _ in RESULTS)
    print('  '.join(f'{kind}: {counts[kind]}' for kind in ('PASS', 'WARN', 'FAIL', 'SKIP')))
    if not agents.get('h1'):
        print('\nACTION: h1 agent is NOT running (it was intentionally stopped in the prior demo).')
        print('At Terminal 2, mininet> prompt, run exactly:')
        print('h1 python3 -u ./agents.py --node-id 10.0.0.1 --server-ip 10.0.0.4 --port 5006 > /tmp/h1-recovery.log 2>&1 &')
        print('Then run this verifier again, and look for [RECOVERED] in /tmp/monitor.log.')
    print('\nCheck the WARN/FAIL messages above before tomorrow\'s demo.')
    return 1 if counts['FAIL'] else 0


if __name__ == '__main__':
    sys.exit(main())
