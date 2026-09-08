#include <pcl/filters/filter.h>
#include <pcl/io/pcd_io.h>
#include <pcl/point_cloud.h>
#include <pcl/point_types.h>

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

namespace {

struct Options {
  std::string input;
  std::string map;
  std::string ground;
  std::string poses;
  std::string path;
  float ground_height = 0.35F;
  float ground_lower_margin = 0.10F;
  int min_ground_points = 10;
  int min_map_points = 100;
  float max_abs_coordinate = 500.0F;
  float max_z_abs = 100.0F;
};

void usage() {
  std::cerr
      << "Usage: lightning_pcd_asset_adapter --input global.pcd --map map.pcd "
         "--ground ground.pcd --poses poses.pcd --path path.txt "
         "[--ground-height 0.35] [--ground-lower-margin 0.10] "
         "[--min-map-points 100] [--max-abs-coordinate 500] [--max-z-abs 100]\n";
}

bool parse_args(int argc, char **argv, Options *options) {
  for (int i = 1; i < argc; ++i) {
    const std::string key = argv[i];
    auto require_value = [&](std::string *target) -> bool {
      if (i + 1 >= argc) {
        std::cerr << "missing value for " << key << "\n";
        return false;
      }
      *target = argv[++i];
      return true;
    };
    if (key == "--input") {
      if (!require_value(&options->input)) return false;
    } else if (key == "--map") {
      if (!require_value(&options->map)) return false;
    } else if (key == "--ground") {
      if (!require_value(&options->ground)) return false;
    } else if (key == "--poses") {
      if (!require_value(&options->poses)) return false;
    } else if (key == "--path") {
      if (!require_value(&options->path)) return false;
    } else if (key == "--ground-height") {
      std::string value;
      if (!require_value(&value)) return false;
      options->ground_height = std::stof(value);
    } else if (key == "--ground-lower-margin") {
      std::string value;
      if (!require_value(&value)) return false;
      options->ground_lower_margin = std::stof(value);
    } else if (key == "--min-ground-points") {
      std::string value;
      if (!require_value(&value)) return false;
      options->min_ground_points = std::stoi(value);
    } else if (key == "--min-map-points") {
      std::string value;
      if (!require_value(&value)) return false;
      options->min_map_points = std::stoi(value);
    } else if (key == "--max-abs-coordinate") {
      std::string value;
      if (!require_value(&value)) return false;
      options->max_abs_coordinate = std::stof(value);
    } else if (key == "--max-z-abs") {
      std::string value;
      if (!require_value(&value)) return false;
      options->max_z_abs = std::stof(value);
    } else {
      std::cerr << "unknown argument: " << key << "\n";
      return false;
    }
  }

  return !options->input.empty() && !options->map.empty() &&
         !options->ground.empty() && !options->poses.empty() &&
         !options->path.empty();
}

bool finite_point(const pcl::PointXYZI &point) {
  return std::isfinite(point.x) && std::isfinite(point.y) &&
         std::isfinite(point.z);
}

bool write_map_and_ground(const Options &options) {
  pcl::PointCloud<pcl::PointXYZI>::Ptr cloud(new pcl::PointCloud<pcl::PointXYZI>);
  if (pcl::io::loadPCDFile(options.input, *cloud) != 0) {
    std::cerr << "failed to load Lightning global PCD: " << options.input << "\n";
    return false;
  }
  std::vector<int> finite_indices;
  pcl::removeNaNFromPointCloud(*cloud, *cloud, finite_indices);
  if (cloud->empty()) {
    std::cerr << "Lightning global PCD is empty after NaN filtering\n";
    return false;
  }
  if (static_cast<int>(cloud->size()) < options.min_map_points) {
    std::cerr << "Lightning global PCD has too few points: " << cloud->size()
              << " (minimum " << options.min_map_points << ")\n";
    return false;
  }

  pcl::PointXYZI min_point;
  pcl::PointXYZI max_point;
  min_point.x = min_point.y = min_point.z = std::numeric_limits<float>::max();
  max_point.x = max_point.y = max_point.z = std::numeric_limits<float>::lowest();
  for (const auto &point : cloud->points) {
    if (!finite_point(point) ||
        std::abs(point.x) > options.max_abs_coordinate ||
        std::abs(point.y) > options.max_abs_coordinate ||
        std::abs(point.z) > options.max_z_abs) {
      std::cerr << "Lightning global PCD has an implausible coordinate; refusing asset registration\n";
      return false;
    }
    min_point.x = std::min(min_point.x, point.x);
    min_point.y = std::min(min_point.y, point.y);
    min_point.z = std::min(min_point.z, point.z);
    max_point.x = std::max(max_point.x, point.x);
    max_point.y = std::max(max_point.y, point.y);
    max_point.z = std::max(max_point.z, point.z);
  }
  if (max_point.x - min_point.x > 2.0F * options.max_abs_coordinate ||
      max_point.y - min_point.y > 2.0F * options.max_abs_coordinate ||
      max_point.z - min_point.z > 2.0F * options.max_z_abs) {
    std::cerr << "Lightning global PCD extent is implausible; refusing asset registration\n";
    return false;
  }

  // The existing Web/asset server parser supports ASCII and uncompressed
  // binary PCD.  Do not write PCL binary_compressed here; otherwise the map can
  // be archived successfully but the frontend falls back to a provisional map.
  if (pcl::io::savePCDFileBinary(options.map, *cloud) != 0) {
    std::cerr << "failed to write map asset: " << options.map << "\n";
    return false;
  }

  std::vector<float> z_values;
  z_values.reserve(cloud->size());
  for (const auto &point : cloud->points) {
    if (finite_point(point)) {
      z_values.push_back(point.z);
    }
  }
  if (z_values.empty()) {
    std::cerr << "Lightning global PCD has no finite z values\n";
    return false;
  }
  std::sort(z_values.begin(), z_values.end());
  const std::size_t floor_index =
      std::min<std::size_t>(z_values.size() - 1, z_values.size() / 20);
  const float floor_z = z_values[floor_index];

  pcl::PointCloud<pcl::PointXYZI>::Ptr ground(new pcl::PointCloud<pcl::PointXYZI>);
  const float lower = floor_z - std::max(0.0F, options.ground_lower_margin);
  const float upper = floor_z + std::max(0.05F, options.ground_height);
  for (const auto &point : cloud->points) {
    if (finite_point(point) && point.z >= lower && point.z <= upper) {
      ground->points.push_back(point);
    }
  }
  if (static_cast<int>(ground->size()) < options.min_ground_points) {
    ground->clear();
    const std::size_t fallback_count =
        std::max<std::size_t>(1, z_values.size() / 10);
    const float fallback_upper = z_values[std::min<std::size_t>(
        z_values.size() - 1, fallback_count - 1)];
    for (const auto &point : cloud->points) {
      if (finite_point(point) && point.z <= fallback_upper) {
        ground->points.push_back(point);
      }
    }
  }
  if (ground->empty()) {
    std::cerr << "failed to derive ground asset from Lightning global PCD\n";
    return false;
  }
  ground->width = static_cast<std::uint32_t>(ground->points.size());
  ground->height = 1;
  ground->is_dense = false;
  if (pcl::io::savePCDFileBinary(options.ground, *ground) != 0) {
    std::cerr << "failed to write ground asset: " << options.ground << "\n";
    return false;
  }
  std::cout << "map_points=" << cloud->size() << "\n";
  std::cout << "ground_points=" << ground->size() << "\n";
  std::cout << "ground_floor_z=" << floor_z << "\n";
  return true;
}

bool write_poses(const Options &options) {
  std::ifstream input(options.path);
  if (!input.is_open()) {
    std::cerr << "failed to open Lightning path file: " << options.path << "\n";
    return false;
  }

  pcl::PointCloud<pcl::PointXYZI> poses;
  std::string line;
  int index = 0;
  while (std::getline(input, line)) {
    if (line.empty() || line.find("timestamp") != std::string::npos) {
      continue;
    }
    std::istringstream stream(line);
    double stamp = 0.0;
    double px = 0.0;
    double py = 0.0;
    double pz = 0.0;
    double qx = 0.0;
    double qy = 0.0;
    double qz = 0.0;
    double qw = 1.0;
    if (!(stream >> stamp >> px >> py >> pz >> qx >> qy >> qz >> qw)) {
      continue;
    }
    if (!std::isfinite(px) || !std::isfinite(py) || !std::isfinite(pz) ||
        std::abs(px) > options.max_abs_coordinate ||
        std::abs(py) > options.max_abs_coordinate ||
        std::abs(pz) > options.max_z_abs) {
      std::cerr << "Lightning path contains an invalid or implausible pose\n";
      return false;
    }
    pcl::PointXYZI point;
    point.x = static_cast<float>(px);
    point.y = static_cast<float>(py);
    point.z = static_cast<float>(pz);
    point.intensity = static_cast<float>(index++);
    poses.points.push_back(point);
  }

  if (poses.empty()) {
    std::cerr << "Lightning path file has no valid poses\n";
    return false;
  }
  poses.width = static_cast<std::uint32_t>(poses.points.size());
  poses.height = 1;
  poses.is_dense = true;
  if (pcl::io::savePCDFileBinary(options.poses, poses) != 0) {
    std::cerr << "failed to write poses asset: " << options.poses << "\n";
    return false;
  }
  std::cout << "poses=" << poses.size() << "\n";
  return true;
}

}  // namespace

int main(int argc, char **argv) {
  Options options;
  if (!parse_args(argc, argv, &options)) {
    usage();
    return 2;
  }
  if (!write_map_and_ground(options)) {
    return 21;
  }
  if (!write_poses(options)) {
    return 22;
  }
  return 0;
}
