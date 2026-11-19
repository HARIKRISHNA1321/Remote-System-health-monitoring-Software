import socket
import json
import time
import argparse
import select

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=5005)
    parser.add_argument("--critical-port",type=int,default=5006)
    parser.add_argument("--cpu",type=float,default=80)
    parser.add_argument("--memory",type=float,default=85)
    parser.add_argument("--timeout",type=float,default=6)
    args=parser.parse_args()

    if args.port==args.critical_port:
        parser.error("Normal and critical ports must be different")

    servers={}

    for port in (args.port,args.critical_port):
        server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        server.bind(("0.0.0.0",port))
        server.setblocking(False)
        servers[server]=port

    nodes={}

    print("Health Monitoring Server Started")
    print("Normal traffic port:",args.port)
    print("Critical traffic port:",args.critical_port)

    try:
        while True:
            readable,_,_=select.select(
                list(servers.keys()),[],[],1
            )

            for server in readable:
                data,address=server.recvfrom(4096)
                port=servers[server]

                try:
                    report=json.loads(data.decode())

                    node=str(report["node_id"])
                    seq=int(report["seq"])
                    sent_time=float(report["timestamp"])

                    current=time.time()
                    latency=(current - sent_time) * 1000
                    previous=nodes.get(node)

                    if previous and previous["failed"]:
                        print("[RECOVERED]",node)

                    if previous:
                        missing=max(0,seq - previous["seq"] - 1)
                        if missing:
                            print("[PACKET LOSS]",node,missing)

                    nodes[node]={
                        "last_seen": current,
                        "seq": seq,
                        "failed": False
                    }

                    cpu=float(report["cpu_percent"])
                    memory=float(report["memory_percent"])

                    traffic=(
                        "CRITICAL / QUEUE 1"
                        if port==args.critical_port
                        else "NORMAL / QUEUE 0"
                    )

                    print(
                        f"\n[{traffic}] [{node}] Sequence: {seq}"
                        f"\nCPU: {cpu:.1f}%"
                        f" | Memory: {memory:.1f}%"
                        f"\nProcesses: {report['process_count']}"
                        f"\nNetwork RX: {report['bytes_recv']}"
                        f" | TX: {report['bytes_sent']}"
                        f"\nReport latency: {latency:.2f} ms"
                    )

                    if cpu>=args.cpu:
                        print("[ALERT] High CPU usage:",node)

                    if memory>=args.memory:
                        print("[ALERT] High memory usage:",node)

                except (
                    ValueError,KeyError,TypeError,
                    UnicodeDecodeError
                ) as e:
                    print("[INVALID REPORT]",e)

            current=time.time()

            for node,info in nodes.items():
                elapsed=current - info["last_seen"]

                if elapsed>args.timeout and not info["failed"]:
                    print(
                        f"\n[NODE DOWN] {node}"
                        f" has not reported for {elapsed:.1f} seconds"
                    )
                    info["failed"]=True

    except KeyboardInterrupt:
        print("\nMonitoring server stopped.")

    finally:
        for server in servers:
            server.close()

if __name__=="__main__":
    main()
