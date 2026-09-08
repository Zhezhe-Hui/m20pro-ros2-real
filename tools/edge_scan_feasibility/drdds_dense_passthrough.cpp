#include <algorithm>
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <mutex>
#include <string>
#include <sys/socket.h>
#include <sys/un.h>
#include <thread>
#include <unistd.h>
#include <vector>

#include "drdds/core/common_type.h"

using Clock = std::chrono::steady_clock;

// Full-field frame layout over the optional Unix socket (little-endian,
// same arch on both ends; consumed by dddmr_dense_cloud_publisher.py):
//   magic[8] "M20PC2DF" | version u32 | sec i32 | nanosec u32 |
//   frame_len u32 | frame bytes |
//   height u32 | width u32 | is_bigendian u8 | is_dense u8 |
//   point_step u32 | row_step u32 | field_count u32 |
//   per field: name_len u32 | name bytes | offset u32 | datatype u8 | count u32
//   data_len u64 | data bytes

namespace {

constexpr char kMagic[8] = {'M', '2', '0', 'P', 'C', '2', 'D', 'F'};
constexpr uint32_t kVersion = 1;

bool write_all(int fd, const void *data, size_t size) {
  const auto *bytes = static_cast<const uint8_t *>(data);
  size_t written = 0;
  while (written < size) {
    const ssize_t n = ::write(fd, bytes + written, size - written);
    if (n <= 0) {
      return false;
    }
    written += static_cast<size_t>(n);
  }
  return true;
}

class SocketSource {
 public:
  explicit SocketSource(std::string path) : path_(std::move(path)) {}

  const std::string &path() const { return path_; }

  bool send_frame(const sensor_msgs::msg::PointCloud2 &cloud) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!ensure_connected_locked()) {
      if (connect_attempts_ % 100 == 0) {
        std::cerr << "dense_socket_connect_pending attempts=" << connect_attempts_
                  << " path=" << path_ << std::endl;
      }
      return false;
    }
    const std::string &frame = cloud.header().frame_id();
    const auto &data = cloud.data();
    const auto &fields = cloud.fields();
    const auto &stamp = cloud.header().stamp();

    const int32_t stamp_sec = stamp.sec();
    const uint32_t stamp_nanosec = stamp.nanosec();
    const uint32_t frame_len = static_cast<uint32_t>(frame.size());
    const uint32_t height = cloud.height();
    const uint32_t width = cloud.width();
    const uint32_t point_step = cloud.point_step();
    const uint32_t row_step = cloud.row_step();
    const uint32_t field_count = static_cast<uint32_t>(fields.size());
    const uint64_t data_len = static_cast<uint64_t>(data.size());

    if (!write_all(fd_, kMagic, sizeof(kMagic)) ||
        !write_all(fd_, &kVersion, sizeof(kVersion)) ||
        !write_all(fd_, &stamp_sec, sizeof(stamp_sec)) ||
        !write_all(fd_, &stamp_nanosec, sizeof(stamp_nanosec)) ||
        !write_all(fd_, &frame_len, sizeof(frame_len)) ||
        !write_all(fd_, &height, sizeof(height)) ||
        !write_all(fd_, &width, sizeof(width))) {
      reset_locked();
      return false;
    }
    const uint8_t bigendian = cloud.is_bigendian() ? 1 : 0;
    const uint8_t dense = cloud.is_dense() ? 1 : 0;
    if (!write_all(fd_, &bigendian, sizeof(bigendian)) ||
        !write_all(fd_, &dense, sizeof(dense)) ||
        !write_all(fd_, &point_step, sizeof(point_step)) ||
        !write_all(fd_, &row_step, sizeof(row_step)) ||
        !write_all(fd_, &field_count, sizeof(field_count)) ||
        !write_all(fd_, frame.data(), frame.size())) {
      reset_locked();
      return false;
    }
    for (const auto &field : fields) {
      const std::string &name = field.name();
      const uint32_t name_len = static_cast<uint32_t>(name.size());
      const uint32_t offset = field.offset();
      const uint8_t datatype = field.datatype();
      const uint32_t count = field.count();
      if (!write_all(fd_, &name_len, sizeof(name_len)) ||
          !write_all(fd_, name.data(), name.size()) ||
          !write_all(fd_, &offset, sizeof(offset)) ||
          !write_all(fd_, &datatype, sizeof(datatype)) ||
          !write_all(fd_, &count, sizeof(count))) {
        reset_locked();
        return false;
      }
    }
    if (!write_all(fd_, &data_len, sizeof(data_len)) ||
        !write_all(fd_, data.data(), data.size())) {
      reset_locked();
      return false;
    }
    return true;
  }

 private:
  bool ensure_connected_locked() {
    if (fd_ >= 0) {
      return true;
    }
    connect_attempts_ += 1;
    fd_ = ::socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd_ < 0) {
      return false;
    }
    sockaddr_un address{};
    address.sun_family = AF_UNIX;
    std::strncpy(address.sun_path, path_.c_str(), sizeof(address.sun_path) - 1);
    if (::connect(fd_, reinterpret_cast<sockaddr *>(&address), sizeof(address)) != 0) {
      ::close(fd_);
      fd_ = -1;
      return false;
    }
    std::cerr << "dense_socket_connected path=" << path_ << std::endl;
    return true;
  }

  void reset_locked() {
    if (fd_ >= 0) {
      ::close(fd_);
      fd_ = -1;
    }
    std::cerr << "dense_socket_disconnected path=" << path_ << std::endl;
  }

  std::string path_;
  std::mutex mutex_;
  int fd_{-1};
  int connect_attempts_{0};
};

}  // namespace

// On-demand dense passthrough for Lightning-LM mapping on 104.
//
// The robot publishes /LIDAR/POINTS with data locators that are only
// reachable on the 33-network segment, so 104 (31-network only) can never
// subscribe it directly.  This binary runs on 106, reads the vendor DrDDS
// /LIDAR/POINTS channel (the only stable entry, see the 2026-07-07 edge scan
// feasibility study) and republishes each frame as-is to a dense topic that
// plain ROS2 subscribers on 104 can consume natively.
//
// Unlike m20pro_edge_scan, it does NOT build /scan or filter points: the
// original x/y/z/intensity/ring/timestamp fields and point_step are kept so
// Lightning sees the real 96-line scan semantics.

struct Stats {
  std::atomic<int> samples{0};
  std::atomic<int> published{0};
  std::atomic<int> points{0};
  std::string frame;
  Clock::time_point first{};
  Clock::time_point last{};
};

int main(int argc, char **argv) {
  std::string input_topic = argc > 1 ? argv[1] : "/LIDAR/POINTS";
  std::string dense_topic = argc > 2 ? argv[2] : "/m20pro/lidar_points_dense";
  int domain = argc > 3 ? std::stoi(argv[3]) : 0;
  bool use_shm = argc > 4 ? std::stoi(argv[4]) != 0 : false;
  std::string prefix = argc > 5 ? argv[5] : "rt";
  std::string frame_id = argc > 6 ? argv[6] : "";
  int max_points = argc > 7 ? std::stoi(argv[7]) : 0;
  int duration_s = argc > 8 ? std::stoi(argv[8]) : 0;
  std::string socket_path = argc > 9 ? argv[9] : "";

  Stats stats;
  // A closed peer must never kill this process mid-frame.
  std::signal(SIGPIPE, SIG_IGN);
  DrDDSManager::Init(domain, "");

  ChannelLidarPointCloud dense_pub(dense_topic, domain, use_shm, prefix);
  SocketSource socket_source(socket_path);
  auto cb = [&stats, &dense_pub, &frame_id, max_points, &socket_source](
                const sensor_msgs::msg::PointCloud2 *msg) {
    auto now = Clock::now();
    int prev = stats.samples.fetch_add(1);
    if (prev == 0) {
      stats.first = now;
    }
    stats.last = now;
    stats.frame = msg->header().frame_id();

    const uint32_t point_step = msg->point_step();
    if (point_step == 0) {
      return;
    }
    const auto &data = msg->data();
    size_t point_count = data.size() / point_step;
    if (msg->width() > 0 && msg->height() > 0) {
      point_count = std::min(
          point_count, static_cast<size_t>(msg->width()) * msg->height());
    }
    if (point_count == 0) {
      return;
    }
    size_t stride = 1;
    if (max_points > 0 && point_count > static_cast<size_t>(max_points)) {
      stride = std::max<size_t>(1, point_count / static_cast<size_t>(max_points));
    }

    sensor_msgs::msg::PointCloud2 out;
    out.header(msg->header());
    if (!frame_id.empty()) {
      out.header().frame_id(frame_id);
    }
    out.height(1);
    out.fields(msg->fields());
    out.is_bigendian(msg->is_bigendian());
    out.point_step(point_step);
    out.is_dense(msg->is_dense());
    const size_t kept = (point_count + stride - 1) / stride;
    out.width(static_cast<uint32_t>(kept));
    out.row_step(point_step * static_cast<uint32_t>(kept));
    std::vector<uint8_t> out_data;
    out_data.reserve(kept * point_step);
    for (size_t i = 0; i < point_count; i += stride) {
      const size_t base = i * point_step;
      out_data.insert(
          out_data.end(), data.begin() + static_cast<long>(base),
          data.begin() + static_cast<long>(base + point_step));
    }
    out.data(std::move(out_data));

    if (dense_pub.Write(&out)) {
      stats.published.fetch_add(1);
      stats.points.store(static_cast<int>(kept));
      if (prev < 3) {
        std::cout << "dense_sample " << (prev + 1)
                  << " in_frame=" << stats.frame
                  << " out_frame=" << out.header().frame_id()
                  << " points=" << kept
                  << " point_step=" << point_step
                  << std::endl;
      }
    }
    if (!socket_source.path().empty()) {
      const auto socket_begin = Clock::now();
      const bool socket_ok = socket_source.send_frame(out);
      const double socket_ms =
          std::chrono::duration<double, std::milli>(Clock::now() - socket_begin).count();
      if (prev > 0 && prev % 20 == 0) {
        std::cout << "dense_timing sample=" << prev
                  << " socket_ms=" << socket_ms
                  << " socket_ok=" << socket_ok
                  << std::endl;
      }
    }
  };
  ChannelLidarPointCloud lidar_sub(cb, input_topic, domain, use_shm, prefix);

  std::cout << "dense_passthrough_start input=" << input_topic
            << " output=" << dense_topic
            << " domain=" << domain
            << " use_shm=" << use_shm
            << " prefix=" << prefix
            << " frame_id=" << (frame_id.empty() ? "(keep)" : frame_id)
            << " max_points=" << max_points
            << " duration_s=" << duration_s
            << " socket=" << (socket_path.empty() ? "(off)" : socket_path)
            << std::endl;

  auto end = Clock::now() + std::chrono::seconds(std::max(0, duration_s));
  while (duration_s <= 0 || Clock::now() < end) {
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
  }

  int sample_count = stats.samples.load();
  double rate_hz = 0.0;
  if (sample_count > 1 && stats.last > stats.first) {
    rate_hz = static_cast<double>(sample_count - 1) /
              std::chrono::duration<double>(stats.last - stats.first).count();
  }

  std::cout << "dense_passthrough_result samples=" << sample_count
            << " rate_hz=" << rate_hz
            << " published=" << stats.published.load()
            << " points=" << stats.points.load()
            << " frame=" << stats.frame
            << std::endl;

  DrDDSManager::Delete();
  return sample_count > 0 ? 0 : 1;
}
