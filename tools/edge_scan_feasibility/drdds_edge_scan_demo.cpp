#include <algorithm>
#include <atomic>
#include <chrono>
#include <cctype>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <deque>
#include <iostream>
#include <limits>
#include <string>
#include <thread>
#include <vector>

#include "drdds/core/common_type.h"

using Clock = std::chrono::steady_clock;

struct Config {
  std::string input_topic{"/LIDAR/POINTS"};
  std::string output_topic{"/m20pro/scan_edge"};
  int duration_s{20};
  int domain{0};
  bool use_shm{false};
  std::string prefix{"rt"};
  float angle_min{-3.14159265358979323846f};
  float angle_max{3.14159265358979323846f};
  float angle_increment{0.005f};
  float range_min{0.2f};
  float range_max{15.0f};
  float height_min{-1.0f};
  float height_max{1.0f};
  float robot_radius{0.25f};
  float max_publish_hz{10.0f};
  float bin_hold_s{0.75f};
  int max_points{20000};
  std::string frame_id{};
  std::string field_profile_name;
  std::string field_profile_hash;
  float dddmr_height_min{-1.5f};
  float dddmr_height_max{2.5f};
  float dddmr_publish_hz{10.0f};
  int dddmr_max_points{12000};
  float dddmr_range_max{30.0f};
  float dddmr_range_min{0.2f};
  float dddmr_hold_s{0.25f};
  std::string edge_cloud_topic{"/m20pro/edge_cloud"};
};

struct Stats {
  std::atomic<int> clouds{0};
  std::atomic<int> scans{0};
  std::atomic<int> finite_bins{0};
  std::atomic<int> current_finite_bins{0};
  std::atomic<int> sampled_points{0};
  std::atomic<int> kept_points{0};
  std::atomic<int> edge_clouds{0};
  std::atomic<int> edge_points{0};
  std::atomic<int> matched{0};
  Clock::time_point first_scan{};
  Clock::time_point last_scan{};
};

struct ScanAccumulator {
  std::vector<float> ranges;
  std::vector<Clock::time_point> updated_at;

  void ensure_size(size_t bins) {
    if (ranges.size() == bins && updated_at.size() == bins) {
      return;
    }
    ranges.assign(bins, std::numeric_limits<float>::infinity());
    updated_at.assign(bins, Clock::time_point{});
  }
};

// Keep the same bounded-age angular hold used by /scan, but retain the
// original point bytes so the DDDMR side receives real x/y/z values rather
// than a LaserScan reconstructed with z=0.
//
// Storage is contiguous (single byte buffer + parallel timestamp vector)
// instead of one heap allocation per point: the 2026-08-13 bisect measured
// the old per-point 26-byte vector/deque layout at ~62% of one core on
// RK3588 (30-40k mallocs per frame at 10Hz).  Output semantics are
// unchanged: same points, same order, same bounded-age window and cap.
struct EdgeCloudAccumulator {
  uint32_t point_step{0};
  std::vector<uint8_t> bytes;
  std::vector<Clock::time_point> stamps;

  void ensure_size(uint32_t step, size_t reserve_points) {
    if (point_step != step) {
      point_step = step;
      bytes.clear();
      stamps.clear();
      bytes.reserve(reserve_points * step);
      stamps.reserve(reserve_points);
    }
    if (bytes.capacity() < reserve_points * step) {
      bytes.reserve(reserve_points * step);
      stamps.reserve(reserve_points);
    }
  }

  void append(const uint8_t *data, size_t size, Clock::time_point updated_at) {
    if (point_step == 0 || data == nullptr || size != point_step) {
      return;
    }
    bytes.insert(bytes.end(), data, data + size);
    stamps.push_back(updated_at);
  }

  void prune(Clock::time_point now, double hold_s, size_t max_points) {
    const double bounded_hold = std::max(0.0, hold_s);
    size_t drop = 0;
    while (drop < stamps.size()) {
      const double age_s = std::chrono::duration<double>(now - stamps[drop]).count();
      if (age_s <= bounded_hold) {
        break;
      }
      drop += 1;
    }
    if (max_points > 0 && stamps.size() - drop > max_points) {
      drop = stamps.size() - max_points;
    }
    if (drop > 0) {
      bytes.erase(bytes.begin(), bytes.begin() + static_cast<long>(drop * point_step));
      stamps.erase(stamps.begin(), stamps.begin() + static_cast<long>(drop));
    }
  }
};

static float read_float32(const std::vector<uint8_t> &data, size_t offset, bool bigendian) {
  if (offset + sizeof(float) > data.size()) {
    return std::numeric_limits<float>::quiet_NaN();
  }
  uint8_t bytes[4];
  if (bigendian) {
    bytes[0] = data[offset + 3];
    bytes[1] = data[offset + 2];
    bytes[2] = data[offset + 1];
    bytes[3] = data[offset + 0];
  } else {
    bytes[0] = data[offset + 0];
    bytes[1] = data[offset + 1];
    bytes[2] = data[offset + 2];
    bytes[3] = data[offset + 3];
  }
  float value = 0.0f;
  std::memcpy(&value, bytes, sizeof(float));
  return value;
}

static bool xyz_offsets(
    const sensor_msgs::msg::PointCloud2 *cloud,
    uint32_t &x_offset,
    uint32_t &y_offset,
    uint32_t &z_offset) {
  bool has_x = false;
  bool has_y = false;
  bool has_z = false;
  for (const auto &field : cloud->fields()) {
    if (field.name() == "x") {
      x_offset = field.offset();
      has_x = true;
    } else if (field.name() == "y") {
      y_offset = field.offset();
      has_y = true;
    } else if (field.name() == "z") {
      z_offset = field.offset();
      has_z = true;
    }
  }
  return has_x && has_y && has_z;
}

static int num_readings(const Config &cfg) {
  return static_cast<int>(std::round((cfg.angle_max - cfg.angle_min) / cfg.angle_increment)) + 1;
}

static void convert_and_publish(
    const sensor_msgs::msg::PointCloud2 *cloud,
    ChannelLaserScan &scan_pub,
    ChannelLidarPointCloud &edge_cloud_pub,
    const Config &cfg,
    Stats &stats,
    ScanAccumulator &accumulator,
    EdgeCloudAccumulator &edge_cloud_accumulator,
    Clock::time_point &last_scan_publish,
    Clock::time_point &last_edge_publish) {
  stats.clouds.fetch_add(1);

  auto now = Clock::now();
  bool scan_publish_due = true;
  if (cfg.max_publish_hz > 0.0f && stats.scans.load() > 0) {
    const double min_period = 1.0 / static_cast<double>(cfg.max_publish_hz);
    scan_publish_due = std::chrono::duration<double>(now - last_scan_publish).count() >= min_period;
  }
  bool edge_publish_due = true;
  if (cfg.dddmr_publish_hz > 0.0f && stats.edge_clouds.load() > 0) {
    const double min_period = 1.0 / static_cast<double>(cfg.dddmr_publish_hz);
    edge_publish_due = std::chrono::duration<double>(now - last_edge_publish).count() >= min_period;
  }
  uint32_t x_offset = 0;
  uint32_t y_offset = 0;
  uint32_t z_offset = 0;
  if (!xyz_offsets(cloud, x_offset, y_offset, z_offset)) {
    return;
  }

  const int bins = num_readings(cfg);
  if (bins <= 0 || cfg.angle_increment <= 0.0f) {
    return;
  }

  std::vector<float> cloud_ranges(
      static_cast<size_t>(bins), std::numeric_limits<float>::infinity());
  const auto &data = cloud->data();
  const uint32_t point_step = cloud->point_step();
  if (point_step == 0) {
    return;
  }
  size_t point_count = data.size() / point_step;
  if (cloud->width() > 0 && cloud->height() > 0) {
    point_count = std::min(point_count, static_cast<size_t>(cloud->width()) * cloud->height());
  }
  if (point_count == 0) {
    return;
  }

  size_t stride = 1;
  if (cfg.max_points > 0 && point_count > static_cast<size_t>(cfg.max_points)) {
    stride = std::max<size_t>(1, point_count / static_cast<size_t>(cfg.max_points));
  }

  int sampled = 0;
  int kept = 0;
  const bool bigendian = cloud->is_bigendian();
  for (size_t i = 0; i < point_count; i += stride) {
    const size_t base = i * point_step;
    const float x = read_float32(data, base + x_offset, bigendian);
    const float y = read_float32(data, base + y_offset, bigendian);
    const float z = read_float32(data, base + z_offset, bigendian);
    sampled += 1;
    if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z)) {
      continue;
    }
    if (z < cfg.height_min || z > cfg.height_max) {
      continue;
    }
    const float dist_sq = x * x + y * y;
    const float min_keep = std::max(cfg.robot_radius, cfg.range_min);
    if (dist_sq < min_keep * min_keep || dist_sq > cfg.range_max * cfg.range_max) {
      continue;
    }
    const float distance = std::sqrt(dist_sq);
    const float angle = std::atan2(y, x);
    int idx = static_cast<int>(std::floor((angle - cfg.angle_min) / cfg.angle_increment));
    if (idx == bins && angle <= cfg.angle_max + 1e-6f) {
      idx = bins - 1;
    }
    if (idx >= 0 && idx < bins && distance < cloud_ranges[static_cast<size_t>(idx)]) {
      cloud_ranges[static_cast<size_t>(idx)] = distance;
      kept += 1;
    }
  }

  accumulator.ensure_size(static_cast<size_t>(bins));
  int current_finite = 0;
  for (size_t idx = 0; idx < cloud_ranges.size(); ++idx) {
    const float value = cloud_ranges[idx];
    if (std::isfinite(value)) {
      accumulator.ranges[idx] = value;
      accumulator.updated_at[idx] = now;
      current_finite += 1;
    }
  }
  stats.current_finite_bins.store(current_finite);
  stats.sampled_points.store(sampled);
  stats.kept_points.store(kept);

  edge_cloud_accumulator.ensure_size(
      point_step, cfg.dddmr_max_points > 0 ? static_cast<size_t>(cfg.dddmr_max_points) : 0);
  const size_t dddmr_stride =
      cfg.dddmr_max_points > 0 && point_count > static_cast<size_t>(cfg.dddmr_max_points)
      ? std::max<size_t>(1, point_count / static_cast<size_t>(cfg.dddmr_max_points))
      : 1;
  for (size_t i = 0; i < point_count; i += dddmr_stride) {
    const size_t base = i * point_step;
    const float x = read_float32(data, base + x_offset, bigendian);
    const float y = read_float32(data, base + y_offset, bigendian);
    const float z = read_float32(data, base + z_offset, bigendian);
    if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z)) {
      continue;
    }
    if (z < cfg.dddmr_height_min || z > cfg.dddmr_height_max) {
      continue;
    }
    const float dist_sq = x * x + y * y;
    if (dist_sq < cfg.dddmr_range_min * cfg.dddmr_range_min ||
        dist_sq > cfg.dddmr_range_max * cfg.dddmr_range_max) {
      continue;
    }
    if (base + point_step <= data.size()) {
      edge_cloud_accumulator.append(data.data() + base, point_step, now);
    }
  }

  // The vendor pointcloud occasionally arrives without the rear hemisphere.
  // Always ingest every cloud, then publish a bounded-age angular aggregate.
  // Throttling before ingestion discards the complementary fragment and makes
  // both the dashboard and Nav2 periodically blind behind the robot.
  int finite = 0;
  bool scan_written = false;
  if (scan_publish_due) {
    std::vector<float> ranges(
        static_cast<size_t>(bins), std::numeric_limits<float>::infinity());
    const double hold_s = std::max(0.0, static_cast<double>(cfg.bin_hold_s));
    for (size_t idx = 0; idx < ranges.size(); ++idx) {
      const auto updated_at = accumulator.updated_at[idx];
      if (updated_at == Clock::time_point{}) {
        continue;
      }
      const double age_s = std::chrono::duration<double>(now - updated_at).count();
      if (age_s <= hold_s && std::isfinite(accumulator.ranges[idx])) {
        ranges[idx] = accumulator.ranges[idx];
        finite += 1;
      }
    }

    sensor_msgs::msg::LaserScan scan;
    scan.header(cloud->header());
    if (!cfg.frame_id.empty()) {
      scan.header().frame_id(cfg.frame_id);
    }
    scan.angle_min(cfg.angle_min);
    scan.angle_max(cfg.angle_min + static_cast<float>(bins - 1) * cfg.angle_increment);
    scan.angle_increment(cfg.angle_increment);
    scan.scan_time(cfg.max_publish_hz > 0.0f ? 1.0f / cfg.max_publish_hz : 0.1f);
    scan.time_increment(scan.scan_time() / std::max(1, bins));
    scan.range_min(cfg.range_min);
    scan.range_max(cfg.range_max);
    scan.ranges(std::move(ranges));
    scan.intensities(std::vector<float>{});
    scan_written = scan_pub.Write(&scan);
    const int previous_scans = stats.scans.fetch_add(1);
    if (previous_scans == 0) {
      stats.first_scan = now;
    }
    stats.last_scan = now;
    last_scan_publish = now;
    stats.finite_bins.store(finite);
  }

  if (edge_publish_due) {
    edge_cloud_accumulator.prune(
        now, static_cast<double>(cfg.dddmr_hold_s),
        cfg.dddmr_max_points > 0 ? static_cast<size_t>(cfg.dddmr_max_points) : 0);
    const size_t edge_points = edge_cloud_accumulator.stamps.size();
    if (edge_points > 0) {
      sensor_msgs::msg::PointCloud2 edge_cloud;
      edge_cloud.header(cloud->header());
      if (!cfg.frame_id.empty()) {
        edge_cloud.header().frame_id(cfg.frame_id);
      }
      edge_cloud.height(1);
      edge_cloud.fields(cloud->fields());
      edge_cloud.is_bigendian(cloud->is_bigendian());
      edge_cloud.point_step(point_step);
      edge_cloud.is_dense(false);
      edge_cloud.width(static_cast<uint32_t>(edge_points));
      edge_cloud.row_step(point_step * static_cast<uint32_t>(edge_points));
      edge_cloud.data(edge_cloud_accumulator.bytes);
      if (edge_cloud_pub.Write(&edge_cloud)) {
        stats.edge_clouds.fetch_add(1);
        stats.edge_points.store(static_cast<int>(edge_points));
        last_edge_publish = now;
      }
    }
  }

  const int scan_count = stats.scans.load();
  if (scan_count > 0 && (scan_count <= 3 || scan_count % 20 == 0)) {
    std::cout << "scan " << scan_count
              << " finite_bins=" << finite
              << " current_finite_bins=" << current_finite
              << " sampled=" << sampled
              << " kept=" << kept
              << " scan_written=" << scan_written
              << " edge_points=" << stats.edge_points.load()
              << " frame=" << (cfg.frame_id.empty() ? cloud->header().frame_id() : cfg.frame_id)
              << std::endl;
  }
}

static Config parse_args(int argc, char **argv) {
  Config cfg;
  if (argc > 1) cfg.input_topic = argv[1];
  if (argc > 2) cfg.output_topic = argv[2];
  if (argc > 3) cfg.duration_s = std::stoi(argv[3]);
  if (argc > 4) cfg.domain = std::stoi(argv[4]);
  if (argc > 5) cfg.use_shm = std::stoi(argv[5]) != 0;
  if (argc > 6) cfg.prefix = argv[6];
  if (argc > 7) cfg.height_min = std::stof(argv[7]);
  if (argc > 8) cfg.height_max = std::stof(argv[8]);
  if (argc > 9) cfg.max_publish_hz = std::stof(argv[9]);
  if (argc > 10) cfg.max_points = std::stoi(argv[10]);
  if (argc > 11) cfg.frame_id = argv[11];
  if (argc > 12) cfg.angle_increment = std::stof(argv[12]);
  if (argc > 13) cfg.range_max = std::stof(argv[13]);
  if (argc > 14) cfg.range_min = std::stof(argv[14]);
  if (argc > 15) cfg.bin_hold_s = std::stof(argv[15]);
  if (argc > 16) cfg.field_profile_name = argv[16];
  if (argc > 17) cfg.field_profile_hash = argv[17];
  if (argc > 18) cfg.dddmr_height_min = std::stof(argv[18]);
  if (argc > 19) cfg.dddmr_height_max = std::stof(argv[19]);
  if (argc > 20) cfg.dddmr_publish_hz = std::stof(argv[20]);
  if (argc > 21) cfg.dddmr_max_points = std::stoi(argv[21]);
  if (argc > 22) cfg.dddmr_range_max = std::stof(argv[22]);
  if (argc > 23) cfg.dddmr_range_min = std::stof(argv[23]);
  if (argc > 24) cfg.dddmr_hold_s = std::stof(argv[24]);
  if (argc > 25) cfg.edge_cloud_topic = argv[25];
  return cfg;
}

int main(int argc, char **argv) {
  if (argc != 26) {
    std::cerr << "m20pro_edge_scan requires the complete generated field profile; "
              << "start it through m20pro-edge-scan-106.service" << std::endl;
    return 2;
  }
  Config cfg = parse_args(argc, argv);
  const bool valid_profile_hash = cfg.field_profile_hash.size() == 64 &&
      std::all_of(
          cfg.field_profile_hash.begin(), cfg.field_profile_hash.end(),
          [](unsigned char ch) { return std::isxdigit(ch) != 0; });
  if (cfg.field_profile_name.empty() || !valid_profile_hash) {
    std::cerr << "invalid generated field profile identity" << std::endl;
    return 2;
  }
  Stats stats;
  ScanAccumulator accumulator;
  Clock::time_point last_scan_publish{};
  Clock::time_point last_edge_publish{};

  DrDDSManager::Init(cfg.domain, "");
  ChannelLaserScan scan_pub(cfg.output_topic, cfg.domain, cfg.use_shm, cfg.prefix);
  ChannelLidarPointCloud edge_cloud_pub(
      cfg.edge_cloud_topic, cfg.domain, cfg.use_shm, cfg.prefix);
  EdgeCloudAccumulator edge_cloud_accumulator;
  auto cb = [&scan_pub, &edge_cloud_pub, &cfg, &stats, &accumulator,
             &edge_cloud_accumulator, &last_scan_publish, &last_edge_publish](
                const sensor_msgs::msg::PointCloud2 *msg) {
    convert_and_publish(
        msg, scan_pub, edge_cloud_pub, cfg, stats, accumulator,
        edge_cloud_accumulator, last_scan_publish, last_edge_publish);
  };
  ChannelLidarPointCloud lidar_sub(cb, cfg.input_topic, cfg.domain, cfg.use_shm, cfg.prefix);

  std::cout << "edge_scan_start input=" << cfg.input_topic
            << " output=" << cfg.output_topic
            << " domain=" << cfg.domain
            << " use_shm=" << cfg.use_shm
            << " prefix=" << cfg.prefix
            << " height=[" << cfg.height_min << "," << cfg.height_max << "]"
            << " angle_increment=" << cfg.angle_increment
            << " range=[" << cfg.range_min << "," << cfg.range_max << "]"
            << " max_publish_hz=" << cfg.max_publish_hz
            << " bin_hold_s=" << cfg.bin_hold_s
            << " max_points=" << cfg.max_points
            << " field_profile=" << cfg.field_profile_name
            << " field_profile_hash=" << cfg.field_profile_hash
            << std::endl;

  auto end = Clock::now() + std::chrono::seconds(std::max(0, cfg.duration_s));
  while (cfg.duration_s <= 0 || Clock::now() < end) {
    stats.matched.store(scan_pub.GetMatchedCount());
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
  }

  const int scan_count = stats.scans.load();
  double rate_hz = 0.0;
  if (scan_count > 1 && stats.last_scan > stats.first_scan) {
    rate_hz = static_cast<double>(scan_count - 1) /
              std::chrono::duration<double>(stats.last_scan - stats.first_scan).count();
  }

  std::cout << "edge_scan_result clouds=" << stats.clouds.load()
            << " scans=" << scan_count
            << " rate_hz=" << rate_hz
            << " finite_bins=" << stats.finite_bins.load()
            << " current_finite_bins=" << stats.current_finite_bins.load()
            << " sampled=" << stats.sampled_points.load()
            << " kept=" << stats.kept_points.load()
            << " matched=" << stats.matched.load()
            << " edge_clouds=" << stats.edge_clouds.load()
            << " edge_points=" << stats.edge_points.load()
            << std::endl;

  DrDDSManager::Delete();
  return scan_count > 0 ? 0 : 1;
}
