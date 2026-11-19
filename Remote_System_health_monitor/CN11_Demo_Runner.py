#!/usr/bin/env python3
"""Fixed-scope, one-shot Project 11 verification runner.

Installed as a root-owned runtime snapshot by install_cn11_launcher.sh.
It refuses to reuse or remove an existing Mininet bridge.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import ast
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time

RUNTIME = Path('/opt/cn-project11')
PROJECT = Path('/home/harikrishna/cn-demo/Team1_Project11_Remote_System_Health_Monitoring')
sys.path.insert(0, str(RUNTIME))

import topology
import CN_Project11_Verifier as verifier


class PreflightBlocked(RuntimeError):
    """The current machine state needs an explicit operator decision."""


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, value):
        for stream in self.streams:
            stream.write(value)
            stream.flush()
        return len(value)

    def flush(self):
        for stream in self.streams:
            stream.flush()


def command(argv, timeout=8):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, '', str(exc)


def emit(kind, title, detail=''):
    print(f'[{kind}] {title}' + (f': {detail}' if detail else ''), flush=True)


def port_open():
    try:
        with socket.create_connection(('127.0.0.1', 6653), timeout=1):
            return True
    except OSError:
        return False


def ensure_controller():
    if port_open():
        emit('PASS', 'Controller port 6653', 'already listening')
        verifier.record('PASS', 'Controller port 6653', 'already listening')
        return
    emit('INFO', 'Starting controller as harikrishna')
    log_dir = Path('/run/cn-project11')
    if not log_dir.exists():
        log_dir.mkdir(mode=0o700)
    dir_stat = log_dir.lstat()
    if not stat.S_ISDIR(dir_stat.st_mode) or dir_stat.st_uid != 0 or dir_stat.st_mode & 0o022:
        raise RuntimeError('Unsafe controller log directory at /run/cn-project11')
    log_path = log_dir / 'controller.log'
    log_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    log = os.fdopen(log_fd, 'a', buffering=1)
    shell_cmd = (
        f'cd {PROJECT} && exec {PROJECT}/.venv/bin/osken-manager '
        '--verbose --ofp-tcp-listen-port 6653 controller.py'
    )
    subprocess.Popen(
        ['runuser', '-u', 'harikrishna', '--', '/bin/bash', '-lc', shell_cmd],
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    for _ in range(20):
        if port_open():
            emit('PASS', 'Controller port 6653', 'started and listening')
            verifier.record('PASS', 'Controller port 6653', 'started and listening')
            return
        time.sleep(0.5)
    raise RuntimeError('Controller failed to listen on 127.0.0.1:6653; see /run/cn-project11/controller.log')


def inspect_existing_state():
    rc, show, err = command(['ovs-vsctl', 'show'])
    if rc:
        raise RuntimeError(f'Open vSwitch is not queryable: {err}')
    print('\n=== Current Open vSwitch state ===\n' + show)

    processes = verifier.proc_table()
    mininet_live = any(
        'mininet:' in args or re.search(r'(^|\s)(mnexec|mininet|topology.py)(\s|$)', args)
        for _, args in processes
    )
    if mininet_live:
        raise RuntimeError('A Mininet process is already running. Refusing to create a duplicate network.')

    rc, bridges, err = command(['ovs-vsctl', 'list-br'])
    if rc:
        raise RuntimeError(f'Could not safely enumerate OVS bridges: {err}')
    if 's1' in bridges.splitlines():
        _, ports, _ = command(['ovs-vsctl', 'list-ports', 's1'])
        _, controller, _ = command(['ovs-vsctl', 'get-controller', 's1'])
        emit('WARN', 'Existing bridge s1 detected', f'ports={ports or "none"}; controller={controller or "none"}')
        raise PreflightBlocked(
            'Refusing to remove/reuse existing s1. Inspect the state above; '
            'an explicit cleanup decision is needed before starting a fresh topology.'
        )


def save_results(log_path, result_rows, started, outcome):
    stamp = dt.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
    lines = [
        '# Project 11 latest automated run',
        '',
        f'- Run started: {started}',
        f'- Run updated: {stamp}',
        f'- Outcome: {outcome}',
        f'- Raw transcript: `results/{log_path.name}`',
        '',
        '| Check | Result | Evidence |',
        '|---|---|---|',
    ]
    for kind, name, details in result_rows:
        safe = details.replace('|', '\\|').replace('\n', ' ')
        lines.append(f'| {name} | {kind} | {safe} |')
    lines.extend([
        '',
        'This section records this run only. Historical measurements elsewhere in the report are not new results.',
    ])
    section_fd, section_name = tempfile.mkstemp(prefix='cn11-report-section-', suffix='.md', dir='/tmp')
    section_path = Path(section_name)
    with os.fdopen(section_fd, 'w', encoding='utf-8') as section_file:
        section_file.write('\n'.join(lines) + '\n')
    user = pwd.getpwnam('harikrishna')
    os.chown(section_path, user.pw_uid, user.pw_gid)
    publisher = r'''import pathlib, shutil, sys
section_path, log_source, project, log_name = sys.argv[1:]
root = pathlib.Path(project)
results = root / "results"
results.mkdir(parents=True, exist_ok=True)
log_destination = results / log_name
shutil.copyfile(log_source, log_destination)
report = root / "FINAL_VERIFICATION_REPORT.md"
old = report.read_text(encoding="utf-8") if report.exists() else "# Project 11 verification report\n"
marker = "# Project 11 latest automated run"
if marker in old:
    old = old[:old.index(marker)].rstrip() + "\n"
section = pathlib.Path(section_path).read_text(encoding="utf-8")
report.write_text(old.rstrip() + "\n\n" + section, encoding="utf-8")
'''
    subprocess.run(
        ['runuser', '-u', 'harikrishna', '--', '/usr/bin/python3', '-c', publisher,
         str(section_path), str(log_path), str(PROJECT), log_path.name],
        check=True,
    )
    section_path.unlink(missing_ok=True)
    log_path.unlink(missing_ok=True)


def failure_recovery(net):
    processes = verifier.proc_table()
    agents = verifier.find_procs(processes, 'agents.py')
    h1_host_pid = net.get('h1').pid
    try:
        h1_netns = os.stat(f'/proc/{h1_host_pid}/ns/net').st_ino
    except OSError:
        h1_netns = None
    expected_script = str(RUNTIME / 'agents.py')
    h1_pid = None
    for pid, args in agents:
        if expected_script not in args or '--node-id 10.0.0.1' not in args or '--port 5006' not in args:
            continue
        try:
            if h1_netns is not None and os.stat(f'/proc/{pid}/ns/net').st_ino == h1_netns:
                h1_pid = pid
                break
        except OSError:
            continue
    if not h1_pid:
        verifier.record('FAIL', 'Failure/recovery test', 'Could not identify the runtime-copy h1 agent in h1 network namespace; no process was signaled')
        return
    log_path = Path('/tmp/monitor.log')
    before = log_path.read_text(errors='replace') if log_path.exists() else ''
    os.kill(h1_pid, signal.SIGTERM)
    verifier.record('PASS', 'Stopped h1 agent for failure test', f'PID {h1_pid}')

    down_seen = False
    deadline = time.time() + 10
    while time.time() < deadline:
        data = log_path.read_text(errors='replace') if log_path.exists() else ''
        if '[NODE DOWN] 10.0.0.1' in data[len(before):]:
            down_seen = True
            break
        time.sleep(0.5)
    verifier.record('PASS' if down_seen else 'FAIL', 'h1 failure detection', 'NODE DOWN recorded' if down_seen else 'timeout event not observed within 10 seconds')

    agent_path = RUNTIME / 'agents.py'
    net.get('h1').cmd(
        f'python3 -u {agent_path} --node-id 10.0.0.1 --server-ip 10.0.0.4 '
        '--port 5006 > /tmp/h1-recovery.log 2>&1 &'
    )
    recovered = False
    deadline = time.time() + 10
    while time.time() < deadline:
        data = log_path.read_text(errors='replace') if log_path.exists() else ''
        if '[RECOVERED] 10.0.0.1' in data[len(before):]:
            recovered = True
            break
        time.sleep(0.5)
    verifier.record('PASS' if recovered else 'FAIL', 'h1 recovery', 'RECOVERED recorded' if recovered else 'recovery event not observed within 10 seconds')


def tc_class_bytes(text):
    counters = {}
    blocks = re.finditer(r'^class htb (\S+)(.*?)(?=^class htb |\Z)', text, re.M | re.S)
    for match in blocks:
        sent = re.search(r'^ Sent (\d+) bytes', match.group(2), re.M)
        if sent:
            counters[match.group(1)] = int(sent.group(1))
    return counters


def full_run():
    started = dt.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
    log_fd, log_name = tempfile.mkstemp(prefix='cn11-live-verification-', suffix='.txt', dir='/tmp')
    log_path = Path(log_name)
    transcript = os.fdopen(log_fd, 'w', encoding='utf-8', buffering=1)
    tee = Tee(sys.stdout, transcript)
    outcome = 'INCOMPLETE'
    stages = (
        'Controller startup',
        'OVS/Mininet preflight',
        'Mininet startup and connectivity',
        'Monitoring reports',
        'OpenFlow and QoS checks',
        'Failure and recovery test',
        'Congestion and HTB comparison',
        'Interactive demo session',
    )
    current_stage = stages[0]
    verifier.RESULTS.clear()
    net = None
    try:
        with contextlib.redirect_stdout(tee):
            print('CN PROJECT 11 — AUTOMATED FULL VERIFICATION')
            print('Started:', started)
            print('Runtime snapshot:', RUNTIME)
            current_stage = stages[0]
            ensure_controller()
            current_stage = stages[1]
            inspect_existing_state()

            current_stage = stages[2]
            net = topology.Mininet(
                topo=topology.HealthMonitoringTopo(), controller=None,
                switch=topology.OVSSwitch, autoSetMacs=True,
            )
            net.addController('c0', controller=topology.RemoteController, ip='127.0.0.1', port=6653)
            print('\n=== Starting Mininet ===')
            net.start()
            topology.configure_qos()
            loss = net.pingAll()
            verifier.record('PASS' if loss == 0 else 'FAIL', 'Mininet pingAll', f'{loss:.1f}% packet loss')
            current_stage = stages[3]
            topology.start_monitoring_services(net)
            time.sleep(2)

            print('\n=== Runtime snapshot and dependencies ===')
            runtime_sources = ('agents.py', 'monitor.py', 'controller.py', 'topology.py')
            for name in runtime_sources:
                try:
                    ast.parse((RUNTIME / name).read_text(encoding='utf-8'), filename=name)
                    verifier.record('PASS', name + ' syntax')
                except (OSError, SyntaxError, UnicodeError) as exc:
                    verifier.record('FAIL', name + ' syntax', str(exc))
            missing_tools = [name for name in ('mn', 'mnexec', 'ovs-vsctl', 'ovs-ofctl', 'tc', 'iperf3') if shutil.which(name) is None]
            verifier.record('FAIL' if missing_tools else 'PASS', 'System tools', ', '.join(missing_tools) if missing_tools else 'Mininet, OVS, tc and iperf3 available')
            psutil_rc, psutil_out, psutil_err = command(['/usr/bin/python3', '-c', 'import psutil; print(psutil.__version__)'])
            verifier.record('PASS' if psutil_rc == 0 else 'FAIL', 'System Python psutil', psutil_out if psutil_rc == 0 else psutil_err)
            current_stage = stages[4]
            bridge = verifier.inspect_sdn()
            before = verifier.inspect_qos(bridge)
            processes = verifier.proc_table()
            agents, monitors = verifier.inspect_monitoring(processes)
            verifier.inspect_ping(processes, verifier.find_procs(processes, 'agents.py'), monitors)
            verifier.inspect_flow_progress(before, agents)

            current_stage = stages[5]
            print('\n=== Failure and recovery ===')
            failure_recovery(net)
            time.sleep(2)
            processes = verifier.proc_table()
            agents, monitors = verifier.inspect_monitoring(processes)
            current_stage = stages[6]
            print('\n=== Congestion test ===')
            _, tc_before, tc_before_err = command(['tc', '-s', 'class', 'show', 'dev', 's1-eth4'])
            tc_before_counts = tc_class_bytes(tc_before)
            tc_sample_start = time.monotonic()
            print('HTB counters before test:\n' + (tc_before or tc_before_err))
            verifier.run_congestion(processes, verifier.find_procs(processes, 'agents.py'), monitors)
            _, tc_after, tc_after_err = command(['tc', '-s', 'class', 'show', 'dev', 's1-eth4'])
            tc_sample_seconds = max(0.001, time.monotonic() - tc_sample_start)
            tc_after_counts = tc_class_bytes(tc_after)
            print('HTB counters after test:\n' + (tc_after or tc_after_err))
            for classid, label in (('1:1', 'Queue 0'), ('1:2', 'Queue 1'), ('1:fffe', 'Parent')):
                if classid in tc_before_counts and classid in tc_after_counts:
                    delta = max(0, tc_after_counts[classid] - tc_before_counts[classid])
                    mbps = delta * 8 / tc_sample_seconds / 1_000_000
                    verifier.record('PASS', label + ' HTB counter sample', f'{mbps:.2f} Mbps over {tc_sample_seconds:.1f}s ({delta} bytes)')
                else:
                    verifier.record('WARN', label + ' HTB counter sample', f'Class {classid} missing in tc output')
            traffic = {}
            for kind, name, detail in verifier.RESULTS:
                if name == 'h2 -> h4 UDP 5201':
                    found = re.search(r'([\d.]+) Mbps received', detail)
                    if found:
                        traffic[5201] = float(found.group(1))
                elif name == 'h1 -> h4 UDP 5202':
                    found = re.search(r'([\d.]+) Mbps received', detail)
                    if found:
                        traffic[5202] = float(found.group(1))
            if len(traffic) == 2 and '1:fffe' in tc_before_counts and '1:fffe' in tc_after_counts:
                iperf_sum = traffic[5201] + traffic[5202]
                parent_delta = max(0, tc_after_counts['1:fffe'] - tc_before_counts['1:fffe'])
                parent_mbps = parent_delta * 8 / tc_sample_seconds / 1_000_000
                verifier.record('WARN', 'iperf / HTB aggregate cross-check', f'iperf receiver averages sum to {iperf_sum:.2f} Mbps; HTB parent sampled {parent_mbps:.2f} Mbps over {tc_sample_seconds:.1f}s (different measurement windows/points)')

            counts = {k: sum(1 for row in verifier.RESULTS if row[0] == k) for k in ('PASS', 'WARN', 'FAIL', 'SKIP')}
            if counts['FAIL']:
                outcome = 'NEEDS ATTENTION'
            elif counts['SKIP']:
                outcome = 'INCOMPLETE'
            elif counts['WARN']:
                outcome = 'PASS WITH WARNINGS'
            else:
                outcome = 'PASS'
            print('\nSummary:', counts)
            print('Returning to Mininet CLI for the demo. Type exit to stop the topology cleanly.')
            current_stage = stages[7]
            topology.CLI(net)
    except PreflightBlocked as exc:
        outcome = 'BLOCKED: existing network state'
        with contextlib.redirect_stdout(tee):
            emit('WARN', 'Safe preflight stop', str(exc))
            verifier.record('WARN', 'Safe preflight stop', str(exc))
            for stage in stages[2:]:
                verifier.record('SKIP', stage, 'Not run because existing OVS/Mininet state needs review')
    except Exception as exc:
        with contextlib.redirect_stdout(tee):
            emit('FAIL', 'Automation stopped safely', str(exc))
            verifier.record('FAIL', current_stage, str(exc))
            for stage in stages[stages.index(current_stage) + 1:]:
                verifier.record('SKIP', stage, 'Not run because the workflow stopped after the error above')
    except KeyboardInterrupt:
        outcome = 'INTERRUPTED'
        with contextlib.redirect_stdout(tee):
            verifier.record('WARN', 'Operator interruption', 'Workflow interrupted; Mininet cleanup will run')
            for stage in stages[stages.index(current_stage) + 1:]:
                verifier.record('SKIP', stage, 'Not run because the workflow was interrupted')
    finally:
        with contextlib.redirect_stdout(tee):
            if net is not None:
                print('Stopping Mininet topology and its host processes...', flush=True)
                try:
                    net.stop()
                    rc, bridges, err = command(['ovs-vsctl', 'list-br'])
                    if rc:
                        outcome = 'NEEDS ATTENTION: OVS cleanup check failed'
                        verifier.record('FAIL', 'Mininet cleanup', f'net.stop returned but bridge state could not be checked: {err}')
                    elif 's1' in bridges.splitlines():
                        outcome = 'NEEDS ATTENTION: residual s1 bridge'
                        verifier.record('FAIL', 'Mininet cleanup', 's1 still exists after net.stop(); left in place for inspection')
                    else:
                        verifier.record('PASS', 'Mininet cleanup', 'net.stop completed and s1 is absent')
                except Exception as exc:
                    outcome = 'NEEDS ATTENTION: topology cleanup error'
                    verifier.record('FAIL', 'Mininet cleanup', str(exc))
            counts = {k: sum(1 for row in verifier.RESULTS if row[0] == k) for k in ('PASS', 'WARN', 'FAIL', 'SKIP')}
            if counts['FAIL'] and not outcome.startswith('BLOCKED'):
                outcome = 'NEEDS ATTENTION'
            elif counts['SKIP'] and outcome == 'PASS':
                outcome = 'INCOMPLETE'
            elif counts['WARN'] and outcome == 'PASS':
                outcome = 'PASS WITH WARNINGS'
            print('\nFinal summary after cleanup:', counts, '| outcome:', outcome)
            transcript.flush()
            transcript.close()
        try:
            user = pwd.getpwnam('harikrishna')
            os.chown(log_path, user.pw_uid, user.pw_gid)
            save_results(log_path, verifier.RESULTS, started, outcome)
        except Exception as exc:
            outcome = 'NEEDS ATTENTION: report update failed'
            print(f'Could not update report: {exc}', file=sys.stderr)
    print(f'Live transcript: {PROJECT / "results" / log_path.name}')
    print(f'Updated report: {PROJECT / "FINAL_VERIFICATION_REPORT.md"}')
    return 0 if outcome in ('PASS', 'PASS WITH WARNINGS') else 1


if __name__ == '__main__':
    if os.geteuid() != 0:
        print('Run through the installed, fixed-scope launcher using sudo.', file=sys.stderr)
        sys.exit(2)
    sys.exit(full_run())
