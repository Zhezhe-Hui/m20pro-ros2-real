#!/usr/bin/env python3
"""Long-lived-participant ROS 2 service probe/call for mapping control.

Short-lived ``ros2 service list/call`` CLI participants intermittently fail to
discover the Lightning mapper under boot-time CPU contention on the RK3588
(verified empirically), while a participant that actually spins converges in
about a second. The mapping control script therefore performs all
discovery-sensitive service interactions through this helper.

Modes:
  exists <service> [--wait S]
      Exit 0 once the service appears in the graph, 1 after the wait budget.
  cloud <topic> [--wait S]
      Exit 0 once the PointCloud2 topic has a publisher AND delivers at least
      one frame; exit 1 when no publisher appears, 4 when no frame arrives.
  call <service> <srv_type> <request_yaml> [--wait S] [--timeout S]
      Wait for the service, call it, print ``field=value`` lines for every
      response field (``response=0`` / ``success=True`` keep the shell-side
      grep contract), exit non-zero on unavailable/timeout.
"""

import argparse
import importlib
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    p_exists = sub.add_parser("exists")
    p_exists.add_argument("service")
    p_exists.add_argument("--wait", type=float, default=15.0)
    p_cloud = sub.add_parser("cloud")
    p_cloud.add_argument("topic")
    p_cloud.add_argument("--wait", type=float, default=6.0)
    p_call = sub.add_parser("call")
    p_call.add_argument("service")
    p_call.add_argument("srv_type")
    p_call.add_argument("request")
    p_call.add_argument("--wait", type=float, default=20.0)
    p_call.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    import rclpy

    rclpy.init()
    node = rclpy.create_node("m20pro_mapping_service_probe")
    try:
        if args.mode == "exists":
            deadline = time.time() + args.wait
            while time.time() < deadline:
                rclpy.spin_once(node, timeout_sec=0.5)
                names = dict(node.get_service_names_and_types())
                if args.service in names:
                    print("found=%s" % args.service)
                    print("types=%s" % ",".join(names[args.service]))
                    return 0
            print("found=")
            return 1

        if args.mode == "cloud":
            from rclpy.qos import (
                DurabilityPolicy,
                HistoryPolicy,
                QoSProfile,
                ReliabilityPolicy,
            )
            from sensor_msgs.msg import PointCloud2

            qos = QoSProfile(
                depth=1,
                reliability=ReliabilityPolicy.BEST_EFFORT,
                history=HistoryPolicy.KEEP_LAST,
                durability=DurabilityPolicy.VOLATILE,
            )
            deadline = time.time() + args.wait
            publishers = 0
            while time.time() < deadline:
                rclpy.spin_once(node, timeout_sec=0.5)
                publishers = node.count_publishers(args.topic)
                if publishers > 0:
                    break
            if publishers == 0:
                print("topic=%s publishers=0 frames=0" % args.topic)
                return 1
            frames = []

            def _on_cloud(msg):
                frames.append(msg)

            node.create_subscription(PointCloud2, args.topic, _on_cloud, qos)
            frame_deadline = time.time() + args.wait
            while not frames and time.time() < frame_deadline:
                rclpy.spin_once(node, timeout_sec=0.2)
            points = int(frames[0].width) * int(frames[0].height) if frames else 0
            print(
                "topic=%s publishers=%d frames=%d points=%d"
                % (args.topic, publishers, len(frames), points)
            )
            return 0 if frames else 4

        import yaml

        # srv_type is "<package>/srv/<Name>"; take head and tail so both
        # two-part and three-part spellings resolve to the generated class.
        parts = [p for p in args.srv_type.split("/") if p]
        package, srv_name = parts[0], parts[-1]
        module = importlib.import_module(package + ".srv")
        srv_type = getattr(module, srv_name)
        client = node.create_client(srv_type, args.service)
        if not client.wait_for_service(timeout_sec=args.wait):
            print("error=service_not_available service=%s" % args.service)
            return 2
        request = srv_type.Request()
        for key, value in (yaml.safe_load(args.request) or {}).items():
            setattr(request, key, value)
        future = client.call_async(request)
        deadline = time.time() + args.timeout
        while not future.done() and time.time() < deadline:
            rclpy.spin_once(node, timeout_sec=0.2)
        if not future.done():
            print("error=call_timeout service=%s" % args.service)
            return 3
        response = future.result()
        for name in response.get_fields_and_field_types():
            print("%s=%s" % (name, getattr(response, name)))
        return 0
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(main())
