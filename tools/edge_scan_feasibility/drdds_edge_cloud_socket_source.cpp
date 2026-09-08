// Receive the vendor DrDDS edge cloud and forward compact XYZ frames over a
// local Unix stream. A separate ROS 2 process owns serialization/publication.

#include <algorithm>
#include <atomic>
#include <chrono>
#include <csignal>
#include <cmath>
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

namespace {
constexpr uint32_t kMagic = 0x4d323043;  // M20C
constexpr uint32_t kVersion = 1;

struct FrameHeader {
  uint32_t magic;
  uint32_t version;
  int32_t stamp_sec;
  uint32_t stamp_nanosec;
  uint32_t point_count;
  uint32_t frame_size;
};

bool write_all(int fd, const void *data, size_t size) {
  const auto *bytes = static_cast<const uint8_t *>(data);
  while (size > 0) {
    const ssize_t written = ::write(fd, bytes, size);
    if (written <= 0) {
      return false;
    }
    bytes += written;
    size -= static_cast<size_t>(written);
  }
  return true;
}

class SocketSource {
public:
  explicit SocketSource(std::string path) : path_(std::move(path)) {}

  ~SocketSource() {
    std::lock_guard<std::mutex> lock(mutex_);
    close_locked();
  }

  bool send(const FrameHeader &header, const std::string &frame,
            const std::vector<float> &points) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!ensure_connected_locked()) {
      return false;
    }
    if (!write_all(fd_, &header, sizeof(header)) ||
        !write_all(fd_, frame.data(), frame.size()) ||
        !write_all(fd_, points.data(), points.size() * sizeof(float))) {
      close_locked();
      return false;
    }
    return true;
  }

private:
  bool ensure_connected_locked() {
    if (fd_ >= 0) {
      return true;
    }
    fd_ = ::socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd_ < 0) {
      return false;
    }
    sockaddr_un address{};
    address.sun_family = AF_UNIX;
    if (path_.size() >= sizeof(address.sun_path)) {
      close_locked();
      return false;
    }
    std::strncpy(address.sun_path, path_.c_str(), sizeof(address.sun_path) - 1);
    if (::connect(fd_, reinterpret_cast<sockaddr *>(&address), sizeof(address)) != 0) {
      close_locked();
      return false;
    }
    return true;
  }

  void close_locked() {
    if (fd_ >= 0) {
      ::close(fd_);
      fd_ = -1;
    }
  }

  std::string path_;
  int fd_{-1};
  std::mutex mutex_;
};

bool find_xyz(const sensor_msgs::msg::PointCloud2 *cloud,
              uint32_t &x, uint32_t &y, uint32_t &z) {
  bool has_x = false;
  bool has_y = false;
  bool has_z = false;
  for (const auto &field : cloud->fields()) {
    if (field.name() == "x") {
      x = field.offset();
      has_x = true;
    } else if (field.name() == "y") {
      y = field.offset();
      has_y = true;
    } else if (field.name() == "z") {
      z = field.offset();
      has_z = true;
    }
  }
  return has_x && has_y && has_z;
}

}  // namespace

int main(int argc, char **argv) {
  // The ROS socket listener is restartable with the real stack. A closed
  // stream must trigger reconnect, not terminate the DrDDS subscriber.
  std::signal(SIGPIPE, SIG_IGN);
  const std::string input_topic = argc > 1 ? argv[1] : "/m20pro/edge_cloud";
  const std::string socket_path = argc > 2 ? argv[2] : "/tmp/m20pro_edge_cloud.sock";
  const int domain = argc > 3 ? std::stoi(argv[3]) : 0;
  const bool use_shm = argc > 4 ? std::stoi(argv[4]) != 0 : false;
  const std::string prefix = argc > 5 ? argv[5] : "rt";
  SocketSource socket_source(socket_path);
  std::atomic<uint64_t> frames{0};

  auto callback = [&](const sensor_msgs::msg::PointCloud2 *cloud) {
    uint32_t x_offset = 0;
    uint32_t y_offset = 0;
    uint32_t z_offset = 0;
    if (!find_xyz(cloud, x_offset, y_offset, z_offset) || cloud->point_step() == 0) {
      return;
    }
    const auto &data = cloud->data();
    const uint32_t step = cloud->point_step();
    const size_t available = data.size() / step;
    // The vendor width/height metadata can describe a fragment rather than
    // the serialized byte payload. The payload is authoritative here.
    const size_t count = available;
    std::vector<float> points;
    points.reserve(count * 3);
    for (size_t index = 0; index < count; ++index) {
      const size_t base = index * step;
      if (base + std::max({x_offset, y_offset, z_offset}) + sizeof(float) > data.size()) {
        break;
      }
      float xyz[3]{};
      std::memcpy(&xyz[0], data.data() + base + x_offset, sizeof(float));
      std::memcpy(&xyz[1], data.data() + base + y_offset, sizeof(float));
      std::memcpy(&xyz[2], data.data() + base + z_offset, sizeof(float));
      if (std::isfinite(xyz[0]) && std::isfinite(xyz[1]) && std::isfinite(xyz[2])) {
        points.insert(points.end(), xyz, xyz + 3);
      }
    }
    if (points.empty()) {
      return;
    }
    const auto &stamp = cloud->header().stamp();
    const auto &frame = cloud->header().frame_id();
    FrameHeader header{
        kMagic, kVersion, stamp.sec(), stamp.nanosec(),
        static_cast<uint32_t>(points.size() / 3), static_cast<uint32_t>(frame.size())};
    if (socket_source.send(header, frame, points)) {
      const uint64_t current = ++frames;
      if (current <= 3 || current % 20 == 0) {
        std::cerr << "edge_socket_source frame=" << current
                  << " points=" << header.point_count << " frame=" << frame << std::endl;
      }
    }
  };

  DrDDSManager::Init(domain, "");
  ChannelLidarPointCloud subscriber(callback, input_topic, domain, use_shm, prefix);
  std::cerr << "edge_socket_source ready input=" << input_topic
            << " socket=" << socket_path << " domain=" << domain
            << " use_shm=" << use_shm << " prefix=" << prefix << std::endl;
  while (true) {
    std::this_thread::sleep_for(std::chrono::seconds(1));
  }
}
