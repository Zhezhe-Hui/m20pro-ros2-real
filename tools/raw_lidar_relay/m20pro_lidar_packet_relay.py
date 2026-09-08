#!/usr/bin/env python3
"""Forward raw RoboSense RSAIRY MSOP packets from the 33-segment to 104.

The M20 vendor firmware below V1.1.7 has no multicast-relay.service (the
manual documents that service for exactly this purpose), so this relay
plays its role: it joins the factory lidar multicast groups on the AOS
host (103) and unicasts every packet to the external compute host (104),
where rslidar_sdk parses them into uncompensated rigid point clouds.

Packet content is untouched: the per-packet PTP timestamps survive the
hop, so point timestamps downstream stay aligned with /IMU.

Run on 103 (AOS).  Config: env or defaults below.
  M20PRO_RELAY_DEST      destination host (default 10.21.31.104)
  M20PRO_RELAY_HEARTBEAT heartbeat file (default /tmp/m20pro_lidar_relay.heartbeat)

Source groups/ports mirror /opt/robot/share/node_driver/config/config.yaml
(front 224.10.10.201:6691, rear 224.10.10.202:6692).
"""

import os
import socket
import struct
import threading
import time

DEST_HOST = os.environ.get("M20PRO_RELAY_DEST", "10.21.31.104")
HEARTBEAT = os.environ.get("M20PRO_RELAY_HEARTBEAT", "/tmp/m20pro_lidar_relay.heartbeat")
RELAYS = (
    ("224.10.10.201", 6691, "front"),
    ("224.10.10.202", 6692, "rear"),
)


def relay_one(group: str, port: int, name: str, counters: dict) -> None:
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rx.bind(("", port))
    membership = struct.pack("4s4s", socket.inet_aton(group), socket.inet_aton("0.0.0.0"))
    rx.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dest = (DEST_HOST, port)
    print("[lidar_relay] %s %s:%d -> %s:%d" % (name, group, port, DEST_HOST, port), flush=True)
    while True:
        data, _ = rx.recvfrom(2048)
        tx.sendto(data, dest)
        counters[name] += 1


def main() -> None:
    counters = {name: 0 for _, _, name in RELAYS}
    for group, port, name in RELAYS:
        worker = threading.Thread(target=relay_one, args=(group, port, name, counters), daemon=True)
        worker.start()
    while True:
        time.sleep(1.0)
        try:
            tmp = HEARTBEAT + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                handle.write("stamp=%.3f front=%d rear=%d dest=%s\n" % (
                    time.time(), counters["front"], counters["rear"], DEST_HOST))
            os.replace(tmp, HEARTBEAT)
        except OSError:
            pass


if __name__ == "__main__":
    main()
