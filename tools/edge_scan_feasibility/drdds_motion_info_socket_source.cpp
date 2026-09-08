// Forward the vendor DrDDS MotionInfo velocity sample to a local Unix stream.
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <sys/socket.h>
#include <sys/un.h>
#include <thread>
#include <unistd.h>

#include "drdds/core/common_type.h"

namespace {
struct Frame { uint32_t magic; uint32_t version; float vx; float vy; float wz; };
constexpr uint32_t kMagic = 0x4d32304f;  // M20O
constexpr uint32_t kVersion = 1;

bool write_all(int fd, const void *data, size_t size) {
  const auto *p = static_cast<const uint8_t *>(data);
  while (size) { const ssize_t n = ::write(fd, p, size); if (n <= 0) return false; p += n; size -= static_cast<size_t>(n); }
  return true;
}

class Socket {
 public:
  explicit Socket(std::string path) : path_(std::move(path)) {}
  ~Socket() { close(); }
  bool send(const Frame &frame) {
    if (!connect()) return false;
    if (!write_all(fd_, &frame, sizeof(frame))) { close(); return false; }
    return true;
  }
 private:
  bool connect() {
    if (fd_ >= 0) return true;
    fd_ = ::socket(AF_UNIX, SOCK_STREAM, 0); if (fd_ < 0) return false;
    sockaddr_un addr{}; addr.sun_family = AF_UNIX;
    if (path_.size() >= sizeof(addr.sun_path)) { close(); return false; }
    std::strncpy(addr.sun_path, path_.c_str(), sizeof(addr.sun_path) - 1);
    if (::connect(fd_, reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) != 0) { close(); return false; }
    return true;
  }
  void close() { if (fd_ >= 0) { ::close(fd_); fd_ = -1; } }
  std::string path_; int fd_{-1};
};
}

int main(int argc, char **argv) {
  std::signal(SIGPIPE, SIG_IGN);
  const std::string topic = argc > 1 ? argv[1] : "/MOTION_INFO";
  const std::string path = argc > 2 ? argv[2] : "/run/m20pro/dddmr_motion_info.sock";
  const int domain = argc > 3 ? std::stoi(argv[3]) : 0;
  const bool shm = argc > 4 ? std::stoi(argv[4]) != 0 : false;
  const std::string prefix = argc > 5 ? argv[5] : "rt";
  Socket socket(path); std::atomic<uint64_t> count{0};
  auto callback = [&](const drdds::msg::MotionInfo *message) {
    const auto &data = message->data();
    Frame frame{kMagic, kVersion, data.vel_x(), data.vel_y(), data.vel_yaw()};
    if (socket.send(frame)) { const auto n = ++count; if (n <= 3 || n % 20 == 0) std::cerr << "motion_socket_source frame=" << n << " vx=" << frame.vx << " vy=" << frame.vy << " wz=" << frame.wz << std::endl; }
  };
  DrDDSManager::Init(domain, "");
  ChannelMotionInfo subscriber(callback, topic, domain, shm, prefix);
  std::cerr << "motion_socket_source ready input=" << topic << " socket=" << path << std::endl;
  while (true) std::this_thread::sleep_for(std::chrono::seconds(1));
}
