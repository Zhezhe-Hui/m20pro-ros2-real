#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/point_cloud2.hpp"
#include "sensor_msgs/msg/point_field.hpp"
#include "std_msgs/msg/string.hpp"

using namespace std::chrono_literals;

class DddmrEdgeCloudAdapter : public rclcpp::Node
{
public:
  DddmrEdgeCloudAdapter()
  : Node("m20pro_dddmr_edge_cloud_adapter")
  {
    input_topic_ = declare_parameter<std::string>("input_topic", "/m20pro/edge_cloud");
    output_topic_ = declare_parameter<std::string>("output_topic", "/dddmr/edge_cloud");
    status_topic_ = declare_parameter<std::string>(
      "status_topic", "/m20pro/dddmr/edge_cloud/status");
    expected_frame_ = normalizeFrame(
      declare_parameter<std::string>("expected_frame", "m20pro_base_link"));
    min_points_ = std::max<int64_t>(1, declare_parameter<int64_t>("min_points", 20));
    max_points_ = std::max<int64_t>(min_points_, declare_parameter<int64_t>("max_points", 20000));
    max_range_m_ = std::max(0.1, declare_parameter<double>("max_range_m", 30.0));
    timeout_s_ = std::max(0.05, declare_parameter<double>("cloud_timeout_s", 0.75));

    auto input_qos = rclcpp::QoS(rclcpp::KeepLast(5)).durability_volatile().best_effort();
    auto output_qos = rclcpp::QoS(rclcpp::KeepLast(2)).durability_volatile().reliable();
    publisher_ = create_publisher<sensor_msgs::msg::PointCloud2>(output_topic_, output_qos);
    status_publisher_ = create_publisher<std_msgs::msg::String>(status_topic_, 10);
    subscription_ = create_subscription<sensor_msgs::msg::PointCloud2>(
      input_topic_, input_qos,
      std::bind(&DddmrEdgeCloudAdapter::onCloud, this, std::placeholders::_1));
    timer_ = create_wall_timer(100ms, std::bind(&DddmrEdgeCloudAdapter::onTimer, this));
    publishStatus(false, "waiting_edge_cloud", "", 0, 0.0);
    RCLCPP_INFO(
      get_logger(), "DDDMR C++ edge-cloud adapter: %s -> %s frame=%s max_points=%zu max_range_m=%.2f",
      input_topic_.c_str(), output_topic_.c_str(), expected_frame_.c_str(), max_points_,
      max_range_m_);
  }

private:
  struct Offsets
  {
    std::size_t x{0};
    std::size_t y{0};
    std::size_t z{0};
    bool valid{false};
  };

  static std::string normalizeFrame(const std::string &value)
  {
    const auto first = value.find_first_not_of('/');
    return first == std::string::npos ? std::string() : value.substr(first);
  }

  static Offsets xyzOffsets(const sensor_msgs::msg::PointCloud2 &cloud)
  {
    Offsets result;
    bool has_x = false;
    bool has_y = false;
    bool has_z = false;
    for (const auto &field : cloud.fields) {
      if (field.datatype != sensor_msgs::msg::PointField::FLOAT32 || field.count < 1) {
        continue;
      }
      if (field.name == "x") {
        result.x = field.offset;
        has_x = true;
      } else if (field.name == "y") {
        result.y = field.offset;
        has_y = true;
      } else if (field.name == "z") {
        result.z = field.offset;
        has_z = true;
      }
    }
    result.valid = has_x && has_y && has_z && cloud.point_step > 0 &&
      result.x + sizeof(float) <= cloud.point_step &&
      result.y + sizeof(float) <= cloud.point_step &&
      result.z + sizeof(float) <= cloud.point_step;
    return result;
  }

  static sensor_msgs::msg::PointCloud2 normalizedCloud(
    const sensor_msgs::msg::PointCloud2 &source,
    std::vector<uint8_t> &&point_data,
    std::size_t point_count)
  {
    sensor_msgs::msg::PointCloud2 output;
    output.header = source.header;
    output.height = 1;
    output.width = static_cast<uint32_t>(point_count);
    output.fields = source.fields;
    output.is_bigendian = source.is_bigendian;
    output.point_step = source.point_step;
    output.row_step = output.width * output.point_step;
    output.is_dense = false;
    output.data = std::move(point_data);
    return output;
  }

  void onCloud(const sensor_msgs::msg::PointCloud2::SharedPtr cloud)
  {
    seen_cloud_ = true;
    last_received_ = std::chrono::steady_clock::now();
    last_frame_ = normalizeFrame(cloud->header.frame_id);
    if (last_frame_.empty()) {
      last_ready_ = false;
      last_code_ = "edge_cloud_frame_missing";
      last_points_ = 0;
      publishStatus(false, last_code_, last_frame_, 0, 0.0);
      return;
    }
    if (last_frame_ != expected_frame_) {
      last_ready_ = false;
      last_code_ = "edge_cloud_frame_mismatch";
      last_points_ = 0;
      publishStatus(false, last_code_, last_frame_, 0, 0.0);
      return;
    }
    if (cloud->is_bigendian) {
      last_ready_ = false;
      last_code_ = "edge_cloud_bigendian_unsupported";
      last_points_ = 0;
      publishStatus(false, last_code_, last_frame_, 0, 0.0);
      return;
    }
    const Offsets offsets = xyzOffsets(*cloud);
    if (!offsets.valid) {
      last_ready_ = false;
      last_code_ = "edge_cloud_xyz_fields_invalid";
      last_points_ = 0;
      publishStatus(false, last_code_, last_frame_, 0, 0.0);
      return;
    }

    // The vendor stream can report width=100 while carrying 12000 serialized
    // points. The payload length is the authoritative count.
    const std::size_t serialized_points = cloud->data.size() / cloud->point_step;
    last_source_points_ = serialized_points;
    const std::size_t inspected_points = std::min<std::size_t>(serialized_points, max_points_);
    const double max_range_squared = max_range_m_ * max_range_m_;
    std::vector<uint8_t> point_data;
    point_data.reserve(inspected_points * cloud->point_step);
    for (std::size_t index = 0; index < inspected_points; ++index) {
      const std::size_t base = index * cloud->point_step;
      float x = 0.0F;
      float y = 0.0F;
      float z = 0.0F;
      std::memcpy(&x, cloud->data.data() + base + offsets.x, sizeof(float));
      std::memcpy(&y, cloud->data.data() + base + offsets.y, sizeof(float));
      std::memcpy(&z, cloud->data.data() + base + offsets.z, sizeof(float));
      if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z)) {
        continue;
      }
      if (static_cast<double>(x) * x + static_cast<double>(y) * y > max_range_squared) {
        continue;
      }
      point_data.insert(
        point_data.end(), cloud->data.begin() + static_cast<std::ptrdiff_t>(base),
        cloud->data.begin() + static_cast<std::ptrdiff_t>(base + cloud->point_step));
    }

    last_points_ = cloud->point_step > 0 ? point_data.size() / cloud->point_step : 0;
    last_ready_ = last_points_ >= min_points_;
    last_code_ = last_ready_ ? "edge_cloud_ready" : "edge_cloud_too_few_points";
    if (last_ready_) {
      publisher_->publish(normalizedCloud(*cloud, std::move(point_data), last_points_));
    }
    publishStatus(last_ready_, last_code_, last_frame_, last_points_, 0.0);
  }

  void onTimer()
  {
    if (!seen_cloud_) {
      publishStatus(false, "waiting_edge_cloud", "", 0, 0.0);
      return;
    }
    const double age_s = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - last_received_).count();
    if (age_s > timeout_s_) {
      last_ready_ = false;
      last_code_ = "edge_cloud_stale";
    }
    publishStatus(last_ready_, last_code_, last_frame_, last_points_, age_s);
  }

  void publishStatus(
    bool ready, const std::string &code, const std::string &frame,
    std::size_t points, double age_s)
  {
    std::ostringstream json;
    json << std::fixed << std::setprecision(3)
         << "{\"component\":\"m20pro_dddmr_edge_cloud\""
         << ",\"ready\":" << (ready ? "true" : "false")
         << ",\"code\":\"" << code << "\""
         << ",\"source_topic\":\"" << input_topic_ << "\""
         << ",\"output_topic\":\"" << output_topic_ << "\""
         << ",\"frame_id\":\"" << frame << "\""
         << ",\"finite_points\":" << points
         << ",\"source_points\":" << last_source_points_
         << ",\"max_points\":" << max_points_
         << ",\"age_s\":" << std::max(0.0, age_s) << "}";
    std_msgs::msg::String message;
    message.data = json.str();
    status_publisher_->publish(message);
  }

  std::string input_topic_;
  std::string output_topic_;
  std::string status_topic_;
  std::string expected_frame_;
  std::size_t min_points_{20};
  std::size_t max_points_{20000};
  std::size_t last_source_points_{0};
  double max_range_m_{30.0};
  double timeout_s_{0.75};
  bool seen_cloud_{false};
  bool last_ready_{false};
  std::string last_code_{"waiting_edge_cloud"};
  std::string last_frame_;
  std::size_t last_points_{0};
  std::chrono::steady_clock::time_point last_received_{};
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr subscription_;
  rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr publisher_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr status_publisher_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char **argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<DddmrEdgeCloudAdapter>());
  rclcpp::shutdown();
  return 0;
}
