#!/usr/bin/env python3
"""Publish MotionInfo socket frames as standard DDDMR odometry."""
import os, socket, struct, threading, math
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Quaternion

FRAME = struct.Struct("<IIfff")
MAGIC, VERSION = 0x4D32304F, 1

class SocketOdomPublisher(Node):
    def __init__(self):
        super().__init__("m20pro_motion_info_odom_adapter")
        self.declare_parameter("socket_path", "/run/m20pro/dddmr_motion_info.sock")
        self.declare_parameter("output_topic", "/m20pro/dddmr/odom")
        self.path = str(self.get_parameter("socket_path").value)
        self.topic = str(self.get_parameter("output_topic").value)
        self.pub = self.create_publisher(Odometry, self.topic, QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE))
        self.lock = threading.Lock(); self.latest = None; self.stop = threading.Event(); self.x = self.y = self.yaw = 0.0; self.last = None
        threading.Thread(target=self._receive, daemon=True).start(); self.create_timer(0.02, self._publish)
    def _read(self, conn):
        data = bytearray()
        while len(data) < FRAME.size:
            part = conn.recv(FRAME.size-len(data))
            if not part: return None
            data.extend(part)
        return FRAME.unpack(data)
    def _receive(self):
        try: os.unlink(self.path)
        except FileNotFoundError: pass
        os.makedirs(os.path.dirname(self.path), exist_ok=True); server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); server.bind(self.path); os.chmod(self.path, 0o666); server.listen(1); server.settimeout(1.0)
        while not self.stop.is_set():
            try: conn, _ = server.accept()
            except socket.timeout: continue
            with conn:
                while not self.stop.is_set():
                    frame = self._read(conn)
                    if frame is None: break
                    if frame[0] == MAGIC and frame[1] == VERSION:
                        with self.lock: self.latest = frame[2:]
        server.close()
    def _publish(self):
        with self.lock: data = self.latest; self.latest = None
        if data is None: return
        vx, vy, wz = (float(v) if math.isfinite(float(v)) else 0.0 for v in data); now = self.get_clock().now(); dt = 0.0 if self.last is None else (now.nanoseconds-self.last)*1e-9; self.last = now.nanoseconds
        if 0 < dt <= .5: self.x += (vx*math.cos(self.yaw)-vy*math.sin(self.yaw))*dt; self.y += (vx*math.sin(self.yaw)+vy*math.cos(self.yaw))*dt; self.yaw = math.atan2(math.sin(self.yaw+wz*dt), math.cos(self.yaw+wz*dt))
        msg = Odometry(); msg.header.stamp = now.to_msg(); msg.header.frame_id = "odom"; msg.child_frame_id = "m20pro_base_link"; msg.pose.pose.position.x = self.x; msg.pose.pose.position.y = self.y; msg.pose.pose.orientation = Quaternion(z=math.sin(self.yaw/2), w=math.cos(self.yaw/2)); msg.twist.twist.linear.x = vx; msg.twist.twist.linear.y = vy; msg.twist.twist.angular.z = wz; self.pub.publish(msg)

def main(args=None):
    rclpy.init(args=args); node = SocketOdomPublisher()
    try: rclpy.spin(node)
    finally: node.stop.set(); node.destroy_node(); rclpy.shutdown()
