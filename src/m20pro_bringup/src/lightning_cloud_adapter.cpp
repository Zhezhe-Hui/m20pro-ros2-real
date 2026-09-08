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

class LightningCloudAdapter : public rclcpp::Node
{
public:
  LightningCloudAdapter()
  : Node("m20pro_lightning_cloud_adapter")
  {
    input_topic_ = declare_parameter<std::string>("input_topic", "/dddmr/edge_cloud");
    output_topic_ = declare_parameter<std::string>("output_topic", "/m20pro/lightning_points");
    status_topic_ = declare_parameter<std::string>(
      "status_topic", "/m20pro/lightning/cloud_adapter/status");
    expected_frame_ = normalizeFrame(
      declare_parameter<std::string>("expected_frame", "m20pro_base_link"));
    output_frame_ = normalizeFrame(
      declare_parameter<std::string>("output_frame", "lidar_link"));
    min_points_ = std::max<int64_t>(1, declare_parameter<int64_t>("min_points", 100));
    max_points_ = std::max<int64_t>(min_points_, declare_parameter<int64_t>("max_points", 30000));
    max_range_m_ = std::max(0.1, declare_parameter<double>("max_range_m", 70.0));
    scan_line_ = std::max<int64_t>(1, declare_parameter<int64_t>("scan_line", 96));
    scan_period_s_ = std::max(0.001, declare_parameter<double>("scan_period_s", 0.1));
    default_intensity_ = static_cast<float>(
      std::max(0.0, declare_parameter<double>("default_intensity", 50.0)));
    timeout_s_ = std::max(0.05, declare_parameter<double>("cloud_timeout_s", 0.75));

    auto input_qos = rclcpp::QoS(rclcpp::KeepLast(5)).durability_volatile().reliable();
    auto output_qos = rclcpp::QoS(rclcpp::KeepLast(5)).durability_volatile().reliable();
    publisher_ = create_publisher<sensor_msgs::msg::PointCloud2>(output_topic_, output_qos);
    status_publisher_ = create_publisher<std_msgs::msg::String>(status_topic_, 10);
    subscription_ = create_subscription<sensor_msgs::msg::PointCloud2>(
      input_topic_, input_qos,
      std::bind(&LightningCloudAdapter::onCloud, this, std::placeholders::_1));
    timer_ = create_wall_timer(100ms, std::bind(&LightningCloudAdapter::onTimer, this));
    publishStatus(false, "waiting_input_cloud", "", 0, 0.0);
    RCLCPP_INFO(
      get_logger(),
      "Lightning cloud adapter: %s -> %s expected_frame=%s output_frame=%s scan_line=%zu max_points=%zu",
      input_topic_.c_str(), output_topic_.c_str(), expected_frame_.c_str(),
      output_frame_.c_str(), scan_line_, max_points_);
  }

private:
  struct FieldInfo
  {
    std::size_t offset{0};
    uint8_t datatype{0};
    bool valid{false};
  };

  struct SourceFields
  {
    FieldInfo x;
    FieldInfo y;
    FieldInfo z;
    FieldInfo intensity;
    FieldInfo ring;
    FieldInfo timestamp;
    bool valid_xyz{false};
  };

  struct OutputPoint
  {
    float x{0.0F};
    float y{0.0F};
    float z{0.0F};
    float intensity{0.0F};
    uint16_t ring{0};
    double timestamp{0.0};
  };

  static std::string normalizeFrame(const std::string &value)
  {
    const auto first = value.find_first_not_of('/');
    return first == std::string::npos ? std::string() : value.substr(first);
  }

  static FieldInfo findField(
    const sensor_msgs::msg::PointCloud2 &cloud, const std::string &name)
  {
    for (const auto &field : cloud.fields) {
      if (field.name == name && field.count >= 1) {
        const auto size = fieldSize(field.datatype);
        if (size > 0 && field.offset + size <= cloud.point_step) {
          return FieldInfo{field.offset, field.datatype, true};
        }
      }
    }
    return FieldInfo{};
  }

  static std::size_t fieldSize(uint8_t datatype)
  {
    switch (datatype) {
      case sensor_msgs::msg::PointField::INT8:
      case sensor_msgs::msg::PointField::UINT8:
        return 1;
      case sensor_msgs::msg::PointField::INT16:
      case sensor_msgs::msg::PointField::UINT16:
        return 2;
      case sensor_msgs::msg::PointField::INT32:
      case sensor_msgs::msg::PointField::UINT32:
      case sensor_msgs::msg::PointField::FLOAT32:
        return 4;
      case sensor_msgs::msg::PointField::FLOAT64:
        return 8;
      default:
        return 0;
    }
  }

  static SourceFields sourceFields(const sensor_msgs::msg::PointCloud2 &cloud)
  {
    SourceFields result;
    result.x = findField(cloud, "x");
    result.y = findField(cloud, "y");
    result.z = findField(cloud, "z");
    result.intensity = findField(cloud, "intensity");
    result.ring = findField(cloud, "ring");
    result.timestamp = findField(cloud, "timestamp");
    result.valid_xyz = cloud.point_step > 0 && result.x.valid && result.y.valid && result.z.valid &&
      result.x.datatype == sensor_msgs::msg::PointField::FLOAT32 &&
      result.y.datatype == sensor_msgs::msg::PointField::FLOAT32 &&
      result.z.datatype == sensor_msgs::msg::PointField::FLOAT32;
    return result;
  }

  static float readFloat32(
    const std::vector<uint8_t> &data, std::size_t base, std::size_t offset)
  {
    float value = 0.0F;
    std::memcpy(&value, data.data() + base + offset, sizeof(float));
    return value;
  }

  static float readNumericAsFloat(
    const std::vector<uint8_t> &data, std::size_t base, const FieldInfo &field,
    float fallback)
  {
    if (!field.valid) {
      return fallback;
    }
    switch (field.datatype) {
      case sensor_msgs::msg::PointField::INT8: {
        int8_t value = 0;
        std::memcpy(&value, data.data() + base + field.offset, sizeof(value));
        return static_cast<float>(value);
      }
      case sensor_msgs::msg::PointField::UINT8: {
        uint8_t value = 0;
        std::memcpy(&value, data.data() + base + field.offset, sizeof(value));
        return static_cast<float>(value);
      }
      case sensor_msgs::msg::PointField::INT16: {
        int16_t value = 0;
        std::memcpy(&value, data.data() + base + field.offset, sizeof(value));
        return static_cast<float>(value);
      }
      case sensor_msgs::msg::PointField::UINT16: {
        uint16_t value = 0;
        std::memcpy(&value, data.data() + base + field.offset, sizeof(value));
        return static_cast<float>(value);
      }
      case sensor_msgs::msg::PointField::INT32: {
        int32_t value = 0;
        std::memcpy(&value, data.data() + base + field.offset, sizeof(value));
        return static_cast<float>(value);
      }
      case sensor_msgs::msg::PointField::UINT32: {
        uint32_t value = 0;
        std::memcpy(&value, data.data() + base + field.offset, sizeof(value));
        return static_cast<float>(value);
      }
      case sensor_msgs::msg::PointField::FLOAT32: {
        float value = 0.0F;
        std::memcpy(&value, data.data() + base + field.offset, sizeof(value));
        return value;
      }
      case sensor_msgs::msg::PointField::FLOAT64: {
        double value = 0.0;
        std::memcpy(&value, data.data() + base + field.offset, sizeof(value));
        return static_cast<float>(value);
      }
      default:
        return fallback;
    }
  }

  static uint16_t readNumericAsUInt16(
    const std::vector<uint8_t> &data, std::size_t base, const FieldInfo &field,
    uint16_t fallback)
  {
    if (!field.valid) {
      return fallback;
    }
    switch (field.datatype) {
      case sensor_msgs::msg::PointField::UINT8: {
        uint8_t value = 0;
        std::memcpy(&value, data.data() + base + field.offset, sizeof(value));
        return static_cast<uint16_t>(value);
      }
      case sensor_msgs::msg::PointField::INT8: {
        int8_t value = 0;
        std::memcpy(&value, data.data() + base + field.offset, sizeof(value));
        return value >= 0 ? static_cast<uint16_t>(value) : fallback;
      }
      case sensor_msgs::msg::PointField::UINT16: {
        uint16_t value = 0;
        std::memcpy(&value, data.data() + base + field.offset, sizeof(value));
        return value;
      }
      case sensor_msgs::msg::PointField::INT16: {
        int16_t value = 0;
        std::memcpy(&value, data.data() + base + field.offset, sizeof(value));
        return value >= 0 ? static_cast<uint16_t>(value) : fallback;
      }
      case sensor_msgs::msg::PointField::UINT32: {
        uint32_t value = 0;
        std::memcpy(&value, data.data() + base + field.offset, sizeof(value));
        return value <= UINT16_MAX ? static_cast<uint16_t>(value) : fallback;
      }
      case sensor_msgs::msg::PointField::INT32: {
        int32_t value = 0;
        std::memcpy(&value, data.data() + base + field.offset, sizeof(value));
        return value >= 0 && value <= UINT16_MAX ? static_cast<uint16_t>(value) : fallback;
      }
      default:
        return fallback;
    }
  }

  static double readNumericAsDouble(
    const std::vector<uint8_t> &data, std::size_t base, const FieldInfo &field,
    double fallback)
  {
    if (!field.valid) {
      return fallback;
    }
    switch (field.datatype) {
      case sensor_msgs::msg::PointField::FLOAT64: {
        double value = 0.0;
        std::memcpy(&value, data.data() + base + field.offset, sizeof(value));
        return value;
      }
      case sensor_msgs::msg::PointField::FLOAT32: {
        float value = 0.0F;
        std::memcpy(&value, data.data() + base + field.offset, sizeof(value));
        return static_cast<double>(value);
      }
      case sensor_msgs::msg::PointField::UINT32: {
        uint32_t value = 0;
        std::memcpy(&value, data.data() + base + field.offset, sizeof(value));
        return static_cast<double>(value);
      }
      case sensor_msgs::msg::PointField::INT32: {
        int32_t value = 0;
        std::memcpy(&value, data.data() + base + field.offset, sizeof(value));
        return static_cast<double>(value);
      }
      default:
        return fallback;
    }
  }

  static double stampToSec(const builtin_interfaces::msg::Time &stamp)
  {
    return static_cast<double>(stamp.sec) + static_cast<double>(stamp.nanosec) * 1e-9;
  }

  static void addField(
    sensor_msgs::msg::PointCloud2 &cloud, const std::string &name,
    uint32_t offset, uint8_t datatype)
  {
    sensor_msgs::msg::PointField field;
    field.name = name;
    field.offset = offset;
    field.datatype = datatype;
    field.count = 1;
    cloud.fields.push_back(field);
  }

  static void writeFloat(std::vector<uint8_t> &data, std::size_t offset, float value)
  {
    std::memcpy(data.data() + offset, &value, sizeof(value));
  }

  static void writeUInt16(std::vector<uint8_t> &data, std::size_t offset, uint16_t value)
  {
    std::memcpy(data.data() + offset, &value, sizeof(value));
  }

  static void writeDouble(std::vector<uint8_t> &data, std::size_t offset, double value)
  {
    std::memcpy(data.data() + offset, &value, sizeof(value));
  }

  sensor_msgs::msg::PointCloud2 robosenseCloud(
    const sensor_msgs::msg::PointCloud2 &source,
    const std::vector<OutputPoint> &points)
  {
    sensor_msgs::msg::PointCloud2 output;
    output.header = source.header;
    output.header.frame_id = output_frame_.empty() ? source.header.frame_id : output_frame_;
    output.height = 1;
    output.width = static_cast<uint32_t>(points.size());
    output.fields.reserve(6);
    addField(output, "x", 0, sensor_msgs::msg::PointField::FLOAT32);
    addField(output, "y", 4, sensor_msgs::msg::PointField::FLOAT32);
    addField(output, "z", 8, sensor_msgs::msg::PointField::FLOAT32);
    addField(output, "intensity", 16, sensor_msgs::msg::PointField::FLOAT32);
    addField(output, "ring", 20, sensor_msgs::msg::PointField::UINT16);
    addField(output, "timestamp", 24, sensor_msgs::msg::PointField::FLOAT64);
    output.is_bigendian = false;
    output.point_step = 32;
    output.row_step = output.width * output.point_step;
    output.is_dense = true;
    output.data.assign(static_cast<std::size_t>(output.row_step), 0);

    for (std::size_t index = 0; index < points.size(); ++index) {
      const std::size_t point_base = index * output.point_step;
      const auto &point = points[index];
      writeFloat(output.data, point_base + 0, point.x);
      writeFloat(output.data, point_base + 4, point.y);
      writeFloat(output.data, point_base + 8, point.z);
      writeFloat(output.data, point_base + 16, point.intensity);
      writeUInt16(output.data, point_base + 20, point.ring);
      writeDouble(output.data, point_base + 24, point.timestamp);
    }
    return output;
  }

  void onCloud(const sensor_msgs::msg::PointCloud2::SharedPtr cloud)
  {
    seen_cloud_ = true;
    last_received_ = std::chrono::steady_clock::now();
    last_frame_ = normalizeFrame(cloud->header.frame_id);
    if (last_frame_.empty()) {
      setStatus(false, "input_cloud_frame_missing", 0);
      return;
    }
    if (last_frame_ != expected_frame_) {
      setStatus(false, "input_cloud_frame_mismatch", 0);
      return;
    }
    if (cloud->is_bigendian) {
      setStatus(false, "input_cloud_bigendian_unsupported", 0);
      return;
    }
    const SourceFields fields = sourceFields(*cloud);
    if (!fields.valid_xyz) {
      setStatus(false, "input_cloud_xyz_fields_invalid", 0);
      return;
    }

    // Match the earlier field-tested 104 bridge behavior: the serialized byte
    // buffer is authoritative because vendor metadata can under-report the
    // real point count.
    const std::size_t serialized_points = cloud->data.size() / cloud->point_step;
    last_source_points_ = serialized_points;
    const std::size_t inspected_points = std::min<std::size_t>(serialized_points, max_points_);
    const double max_range_squared = max_range_m_ * max_range_m_;
    const bool has_ring = fields.ring.valid;
    const bool has_timestamp = fields.timestamp.valid;
    const double start_time = stampToSec(cloud->header.stamp);
    const double denominator = inspected_points > 1 ? static_cast<double>(inspected_points - 1) : 1.0;
    std::vector<OutputPoint> points;
    points.reserve(inspected_points);
    for (std::size_t index = 0; index < inspected_points; ++index) {
      const std::size_t base = index * cloud->point_step;
      if (base + cloud->point_step > cloud->data.size()) {
        break;
      }
      const float x = readFloat32(cloud->data, base, fields.x.offset);
      const float y = readFloat32(cloud->data, base, fields.y.offset);
      const float z = readFloat32(cloud->data, base, fields.z.offset);
      const float intensity = readNumericAsFloat(
        cloud->data, base, fields.intensity, default_intensity_);
      if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z)) {
        continue;
      }
      if (static_cast<double>(x) * x + static_cast<double>(y) * y > max_range_squared) {
        continue;
      }
      const auto synthetic_ring = static_cast<uint16_t>(index % scan_line_);
      const double synthetic_timestamp = start_time + scan_period_s_ * index / denominator;
      const double timestamp = readNumericAsDouble(
        cloud->data, base, fields.timestamp, synthetic_timestamp);
      OutputPoint point;
      point.x = x;
      point.y = y;
      point.z = z;
      point.intensity = std::isfinite(intensity) ? intensity : default_intensity_;
      point.ring = readNumericAsUInt16(cloud->data, base, fields.ring, synthetic_ring);
      point.timestamp = std::isfinite(timestamp) ? timestamp : synthetic_timestamp;
      points.push_back(point);
    }

    if (has_timestamp) {
      std::stable_sort(
        points.begin(), points.end(),
        [](const OutputPoint &left, const OutputPoint &right) {
          return left.timestamp < right.timestamp;
        });
    }

    last_points_ = points.size();
    last_ring_source_ = has_ring;
    last_timestamp_source_ = has_timestamp;
    if (last_points_ < min_points_) {
      setStatus(false, "input_cloud_too_few_points", last_points_);
      return;
    }
    publisher_->publish(robosenseCloud(*cloud, points));
    setStatus(true, "lightning_cloud_ready", last_points_);
  }

  void onTimer()
  {
    if (!seen_cloud_) {
      publishStatus(false, "waiting_input_cloud", "", 0, 0.0);
      return;
    }
    const double age_s = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - last_received_).count();
    if (age_s > timeout_s_) {
      publishStatus(false, "input_cloud_stale", last_frame_, last_points_, age_s);
    } else {
      publishStatus(last_ready_, last_code_, last_frame_, last_points_, age_s);
    }
  }

  void setStatus(bool ready, const std::string &code, std::size_t points)
  {
    last_ready_ = ready;
    last_code_ = code;
    last_points_ = points;
    publishStatus(ready, code, last_frame_, points, 0.0);
  }

  void publishStatus(
    bool ready, const std::string &code, const std::string &frame,
    std::size_t points, double age_s)
  {
    std::ostringstream json;
    json << std::fixed << std::setprecision(3)
         << "{\"component\":\"m20pro_lightning_cloud_adapter\""
         << ",\"ready\":" << (ready ? "true" : "false")
         << ",\"code\":\"" << code << "\""
         << ",\"source_topic\":\"" << input_topic_ << "\""
         << ",\"output_topic\":\"" << output_topic_ << "\""
         << ",\"frame_id\":\"" << frame << "\""
         << ",\"output_frame\":\"" << output_frame_ << "\""
         << ",\"finite_points\":" << points
         << ",\"source_points\":" << last_source_points_
         << ",\"max_points\":" << max_points_
         << ",\"scan_line\":" << scan_line_
         << ",\"ring_source\":" << (last_ring_source_ ? "true" : "false")
         << ",\"timestamp_source\":" << (last_timestamp_source_ ? "true" : "false")
         << ",\"age_s\":" << std::max(0.0, age_s) << "}";
    std_msgs::msg::String message;
    message.data = json.str();
    status_publisher_->publish(message);
  }

  std::string input_topic_;
  std::string output_topic_;
  std::string status_topic_;
  std::string expected_frame_;
  std::string output_frame_;
  std::size_t min_points_{100};
  std::size_t max_points_{30000};
  double max_range_m_{70.0};
  std::size_t scan_line_{96};
  double scan_period_s_{0.1};
  float default_intensity_{50.0F};
  double timeout_s_{0.75};
  bool seen_cloud_{false};
  bool last_ready_{false};
  std::string last_code_{"waiting_input_cloud"};
  std::string last_frame_;
  std::size_t last_source_points_{0};
  std::size_t last_points_{0};
  bool last_ring_source_{false};
  bool last_timestamp_source_{false};
  std::chrono::steady_clock::time_point last_received_{};
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr subscription_;
  rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr publisher_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr status_publisher_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char **argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<LightningCloudAdapter>());
  rclcpp::shutdown();
  return 0;
}
