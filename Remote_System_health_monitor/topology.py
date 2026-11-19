from mininet.net import Mininet
from mininet.topo import Topo
from mininet.node import OVSSwitch,RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel,info
from pathlib import Path
import subprocess
import shlex
import time

class HealthMonitoringTopo(Topo):

    def build(self):

        s1=self.addSwitch(
            's1',
            protocols='OpenFlow13',
            failMode='secure'
        )

        h1=self.addHost('h1',ip='10.0.0.1/24')
        h2=self.addHost('h2',ip='10.0.0.2/24')
        h3=self.addHost('h3',ip='10.0.0.3/24')
        h4=self.addHost('h4',ip='10.0.0.4/24')

        self.addLink(h1,s1)
        self.addLink(h2,s1)
        self.addLink(h3,s1)
        self.addLink(h4,s1)

def configure_qos():

    import re

    info('*** Configuring HTB QoS\n')

    port=subprocess.run(
        ['ovs-vsctl','get','Interface','s1-eth4','ofport'],
        capture_output=True,
        text=True,
        check=True
    ).stdout.strip()

    if port!='4':
        raise RuntimeError(
            f'Expected h4 switch port 4, but found {port}'
        )

    attached_qos=subprocess.run(
        ['ovs-vsctl','get','Port','s1-eth4','qos'],
        capture_output=True,
        text=True,
        check=True
    ).stdout.strip().strip('"')

    tagged_qos_ids=set(subprocess.run(
        [
            'ovs-vsctl','--data=bare','--no-heading',
            '--columns=_uuid','find','QoS',
            'external_ids:project=team1-project11'
        ],
        capture_output=True,
        text=True,
        check=True
    ).stdout.split())

    port_names=subprocess.run(
        [
            'ovs-vsctl','--data=bare','--no-heading',
            '--columns=name','list','Port'
        ],
        capture_output=True,
        text=True,
        check=True
    ).stdout.splitlines()

    port_qos={}

    for port_name in port_names:
        port_name=port_name.strip().strip('"')

        if not port_name:
            continue

        port_qos[port_name]=subprocess.run(
            ['ovs-vsctl','get','Port',port_name,'qos'],
            capture_output=True,
            text=True,
            check=True
        ).stdout.strip().strip('"')

    attached_qos_ids={
        qos_id for qos_id in port_qos.values()
        if re.fullmatch(r'[0-9a-fA-F-]{36}',qos_id)
    }

    # Remove only this project's tagged QoS rows that no OVS port uses.
    old_qos_ids=tagged_qos_ids-attached_qos_ids

    if attached_qos not in ('[]',''):
        shared=any(
            port_name!='s1-eth4' and qos_id==attached_qos
            for port_name,qos_id in port_qos.items()
        )

        if shared:
            info('*** Existing QoS is shared with another OVS port; preserving its QoS and Queue records\n')
        else:
            old_qos_ids.add(attached_qos)

    old_queue_ids=set()

    all_qos_output=subprocess.run(
        ['ovs-vsctl','--columns=_uuid,queues','list','QoS'],
        capture_output=True,
        text=True,
        check=True
    ).stdout

    qos_rows=[]

    for block in re.split(r'\n\s*\n',all_qos_output):
        qos_match=re.search(
            r'_uuid\s*:\s*([0-9a-fA-F-]{36})',
            block
        )

        if qos_match:
            queues_match=re.search(
                r'^queues\s*:\s*(.*)$',
                block,
                re.M
            )

            qos_rows.append((
                qos_match.group(1),
                set(re.findall(
                    r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',
                    queues_match.group(1) if queues_match else ''
                ))
            ))

    for qos_id in old_qos_ids:
        queues=subprocess.run(
            ['ovs-vsctl','get','QoS',qos_id,'queues'],
            capture_output=True,
            text=True,
            check=True
        ).stdout

        queue_ids=set(
            re.findall(
                r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',
                queues
            )
        )

        for queue_id in queue_ids:
            referenced_elsewhere=any(
                other_qos_id not in old_qos_ids and queue_id in other_queues
                for other_qos_id,other_queues in qos_rows
            )

            if not referenced_elsewhere:
                old_queue_ids.add(queue_id)

    subprocess.run(
        ['ovs-vsctl','--if-exists','clear','Port','s1-eth4','qos'],
        check=True
    )

    for qos_id in old_qos_ids:
        subprocess.run(
            ['ovs-vsctl','--if-exists','destroy','QoS',qos_id],
            check=True
        )

    for queue_id in old_queue_ids:
        subprocess.run(
            ['ovs-vsctl','--if-exists','destroy','Queue',queue_id],
            check=True
        )

    info(f'*** Removed {len(old_qos_ids)} previous QoS record(s)\n')
    info(f'*** Removed {len(old_queue_ids)} previous Queue record(s)\n')

    command=[
        'ovs-vsctl',
        '--','set','Port','s1-eth4','qos=@qos',
        '--','--id=@qos','create','QoS',
        'type=linux-htb',
        'other_config:max-rate=10000000',
        'external_ids:project=team1-project11',
        'queues:0=@q0',
        'queues:1=@q1',
        '--','--id=@q0','create','Queue',
        'other_config:min-rate=1000000',
        'other_config:max-rate=10000000',
        'other_config:priority=10',
        '--','--id=@q1','create','Queue',
        'other_config:min-rate=8000000',
        'other_config:max-rate=10000000',
        'other_config:priority=0'
    ]

    subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True
    )

    info('*** QoS successfully attached to s1-eth4\n')
    info('*** Parent rate: 10 Mbps\n')
    info('*** Queue 0: 1 Mbps minimum, 10 Mbps maximum\n')
    info('*** Queue 1: 8 Mbps minimum, 10 Mbps maximum\n')

def start_monitoring_services(net):

    project_dir=Path(__file__).resolve().parent

    monitor_file=shlex.quote(
        str(project_dir / 'monitor.py')
    )

    agent_file=shlex.quote(
        str(project_dir / 'agents.py')
    )

    info('*** Starting health monitoring server on h4\n')

    net.get('h4').cmd(
        f'python3 -u {monitor_file}'
        f' --port 5005 --critical-port 5006'
        f' --timeout 6 > /tmp/monitor.log 2>&1 &'
    )

    time.sleep(1)

    agents=[
        ('h1','10.0.0.1',5006),
        ('h2','10.0.0.2',5005),
        ('h3','10.0.0.3',5005)
    ]

    for host_name,node_ip,port in agents:

        info(f'*** Starting agent on {host_name}\n')

        net.get(host_name).cmd(
            f'python3 -u {agent_file}'
            f' --node-id {node_ip}'
            f' --server-ip 10.0.0.4'
            f' --port {port}'
            f' > /tmp/{host_name}.log 2>&1 &'
        )

    time.sleep(1)

    if not net.get('h4').cmd('pgrep -f monitor.py'):
        raise RuntimeError('Monitoring server failed to start')

    for host_name,node_ip,port in agents:

        if not net.get(host_name).cmd('pgrep -f agents.py'):
            raise RuntimeError(
                f'Health agent failed to start on {host_name}'
            )

    info('*** Monitoring server and all agents started\n')

def run():

    topo=HealthMonitoringTopo()

    net=Mininet(
        topo=topo,
        controller=None,
        switch=OVSSwitch,
        autoSetMacs=True
    )

    net.addController(
        'c0',
        controller=RemoteController,
        ip='127.0.0.1',
        port=6653
    )

    try:

        info('*** Starting network\n')
        net.start()

        configure_qos()

        info('*** Testing connectivity\n')
        net.pingAll()

        start_monitoring_services(net)

        info('*** Network is ready\n')
        CLI(net)

    finally:

        info('*** Stopping network\n')
        net.stop()

if __name__=='__main__':

    setLogLevel('info')
    run()
