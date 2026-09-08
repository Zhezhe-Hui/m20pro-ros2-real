"""Lightweight LeGO feature-channel splitter replacing lego_loam_bor mcl_feature.

mcl_3dl (official DDDMR MCL) consumes four synchronized /laser_cloud_* channels
but only actually uses two of them in its measurement model: laser_cloud_flat
(ground) and laser_cloud_less_sharp (non-ground).  The vendored mcl_feature
binary (LeGO-LOAM ImageProjection) needs a structured multi-ring scan with a
float ring field and produced empty output on the M20Pro's filtered xyz cloud,
starving mcl_3dl forever.  This node derives the two channels with a simple
z-band split of the normalized edge cloud, which is all the likelihood model
needs (the ground channel is an optional weighting input that degrades
gracefully when sparse).
"""

import struct

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import PointCloud2, PointField


def _empty_cloud(header, stamp_source) -> PointCloud2:
    msg = PointCloud2()
    msg.header = header
    msg.height = 1
    msg.width = 0
    msg.fields = [
        PointField(name="x", offset=0, datatype=PointField.FLOAT32, count=1),
        PointField(name="y", offset=4, datatype=PointField.FLOAT32, count=1),
        PointField(name="z", offset=8, datatype=PointField.FLOAT32, count=1),
        PointField(name="intensity", offset=12, datatype=PointField.FLOAT32, count=1),
    ]
    msg.is_bigendian = False
    msg.point_step = 16
    msg.row_step = 0
    msg.is_dense = False
    msg.data = b""
    return msg


def _pack_points(header, pts) -> PointCloud2:
    msg = PointCloud2()
    msg.header = header
    msg.height = 1
    msg.width = len(pts)
    msg.fields = [
        PointField(name="x", offset=0, datatype=PointField.FLOAT32, count=1),
        PointField(name="y", offset=4, datatype=PointField.FLOAT32, count=1),
        PointField(name="z", offset=8, datatype=PointField.FLOAT32, count=1),
        PointField(name="intensity", offset=12, datatype=PointField.FLOAT32, count=1),
    ]
    msg.is_bigendian = False
    msg.point_step = 16
    msg.row_step = 16 * len(pts)
    msg.is_dense = False
    # intensity 必须非零: mcl_3dl 的 likelihood 模型对 less_sharp 通道做
    # score += dist^2 / intensity, 零强度会把似然打成 inf/nan, 粒子永不收敛。
    msg.data = b"".join(struct.pack("<ffff", x, y, z, 1.0) for x, y, z in pts)
    return msg


class DddmrFeatureSplit(Node):
    def __init__(self) -> None:
        super().__init__("m20pro_dddmr_feature_split")
        self.declare_parameter("input_topic", "/dddmr/edge_cloud")
        self.declare_parameter("ground_z_max", -0.10)
        self.declare_parameter("less_sharp_stride", 4)
        qos_in = QoSProfile(depth=3, reliability=ReliabilityPolicy.BEST_EFFORT,
                            history=HistoryPolicy.KEEP_LAST)
        qos_out = QoSProfile(depth=3, reliability=ReliabilityPolicy.RELIABLE,
                             history=HistoryPolicy.KEEP_LAST)
        self.pub_flat = self.create_publisher(PointCloud2, "laser_cloud_flat", qos_out)
        self.pub_less_flat = self.create_publisher(PointCloud2, "laser_cloud_less_flat", qos_out)
        self.pub_sharp = self.create_publisher(PointCloud2, "laser_cloud_sharp", qos_out)
        self.pub_less_sharp = self.create_publisher(PointCloud2, "laser_cloud_less_sharp", qos_out)
        self.create_subscription(
            PointCloud2,
            str(self.get_parameter("input_topic").value),
            self._on_cloud,
            qos_in,
        )

        self.get_logger().info(
            "dddmr feature split: %s -> laser_cloud_* (ground_z_max=%.2f stride=%d)"
            % (
                str(self.get_parameter("input_topic").value),
                float(self.get_parameter("ground_z_max").value),
                int(self.get_parameter("less_sharp_stride").value),
            )
        )

    def _on_cloud(self, msg: PointCloud2) -> None:
        ground_z_max = float(self.get_parameter("ground_z_max").value)
        stride = max(1, int(self.get_parameter("less_sharp_stride").value))
        step = msg.point_step
        n = msg.width
        if n == 0 or step < 12:
            return
        vals = struct.unpack_from("<%df" % (n * (step // 4)), msg.data, 0)
        per = step // 4
        ground = []
        less_sharp = []
        for i in range(n):
            b = i * per
            x = vals[b]
            y = vals[b + 1]
            z = vals[b + 2]
            if z <= ground_z_max:
                ground.append((x, y, z))
            elif i % stride == 0:
                less_sharp.append((x, y, z))
        header = msg.header
        self.pub_flat.publish(_pack_points(header, ground))
        self.pub_less_flat.publish(_pack_points(header, ground))
        self.pub_sharp.publish(_empty_cloud(header, msg))
        self.pub_less_sharp.publish(_pack_points(header, less_sharp))


def main() -> None:
    rclpy.init()
    node = DddmrFeatureSplit()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
