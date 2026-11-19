import socket
import json
import time
import argparse
import psutil

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--node-id",required=True)
    parser.add_argument("--server-ip",default="127.0.0.1")
    parser.add_argument("--port",type=int,default=5005)
    parser.add_argument("--interval",type=float,default=2)
    args=parser.parse_args()

    if args.interval<=0:
        parser.error("Interval must be greater than zero")

    client=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)

    seq=0

    print("Starting Health Agent:",args.node_id)

    try:
        while True:
            seq+=1

            cpu=psutil.cpu_percent(interval=0.2)
            memory=psutil.virtual_memory().percent
            processes=len(psutil.pids())
            network=psutil.net_io_counters()

            report={
                "node_id": args.node_id,
                "seq": seq,
                "timestamp": time.time(),
                "cpu_percent": cpu,
                "memory_percent": memory,
                "process_count": processes,
                "bytes_sent": network.bytes_sent,
                "bytes_recv": network.bytes_recv
            }

            message=json.dumps(report).encode()

            client.sendto(
                message,
                (args.server_ip,args.port)
            )

            print(
                f"Sent report {seq}"
                f" | CPU: {cpu}%"
                f" | Memory: {memory}%"
            )

            time.sleep(max(0,args.interval - 0.2))

    except KeyboardInterrupt:
        print("\nAgent stopped.")

    finally:
        client.close()

if __name__=="__main__":
    main()
