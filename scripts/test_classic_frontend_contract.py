#!/usr/bin/env python3
"""Source checks for the simplified v3 frontend."""

from html.parser import HTMLParser
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/m20pro_cloud_bridge/m20pro_cloud_bridge/static"


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):  # type: ignore[override]
        if tag in {"script", "style"}:
            self._skip_depth += 1

    def handle_endtag(self, tag):  # type: ignore[override]
        if tag in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):  # type: ignore[override]
        if not self._skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def extract_visible_text(html: str) -> str:
    parser = VisibleTextParser()
    parser.feed(html)
    return parser.text()


def main() -> None:
    html = (STATIC / "dashboard.html").read_text(encoding="utf-8")
    script = (STATIC / "dashboard.js").read_text(encoding="utf-8")
    camera_gateway = (ROOT / "systemd/m20pro-camera-webrtc-104.yml").read_text(encoding="utf-8")
    visible = extract_visible_text(html)

    for token in (
        "空间标点",
        "开始建图",
        "结束建图",
        "任务编排",
        "生成任务",
    ):
        assert token in visible, token

    for forbidden in ("DDDMR", "dddmr", "Nav2", "nav2", "GNSS", "GPS", "影子", "基础模式"):
        assert forbidden not in visible, forbidden

    for element_id in (
        "mapDddmrMapAssetsStatus",
        "mapDddmrRefreshAssetsBtn",
        "mapDddmrAssetWorkspace",
        "markZ",
        "startMappingBtn",
        "finishMappingBtn",
        "taskPointList",
    ):
        assert f'id="{element_id}"' in html, element_id

    for forbidden_id in (
        "crossFloorPointPool",
        "crossFloorPointSearch",
        "createCrossFloorTaskBtn",
        "clearCrossFloorDraftBtn",
        "crossFloorDraft",
        "mapEditorBtn",
        "mapEditorToolbar",
        "mapSelect",
        "selectMapBtn",
        "reloadMapsBtn",
        "deleteMapBtn",
        "mapList",
    ):
        assert forbidden_id not in html, forbidden_id

    for token in (
        "renderUnifiedSpaceView",
        "spatialTaskAnnotations",
        "spatialTaskAnnotationById",
        "spatialRoutePreviewForIds",
        "renderUnifiedTaskRouteHint",
        "currentMarkZ",
        '"/api/tasks/cross_floor"',
        "markZ",
        "updateCreateTaskButton",
        "renderDddmrFieldTestMode",
        "buildSpatialMap",
        "buildSpatialRenderModel",
        "drawSpatialRenderCells3d",
        "drawSpatialRenderCellsTopdown",
        "drawLiveCloud3d",
        "drawRobotModel3d",
        "live_cloud",
        "liveRobotPose3d",
        "mapcloud_samples",
        "mapground_samples",
        "renderDddmrAssetWorkspace",
    ):
        assert token in script, token

    assert "切到 DDDMR" not in script
    assert "mapEditor" not in script
    assert '"/api/maps/edit"' not in script
    assert '"/api/maps/select"' not in script
    assert '"/api/mapping/import_active_map"' not in script
    assert 'fetchJson("/api/map")' not in script
    assert 'fetchJson(`/api/map_file' not in script
    assert "/scan" not in html
    assert "/scan" not in script
    assert "可导航" not in script
    assert "建图模式" not in visible
    assert "现场楼层" not in visible
    assert "统一空间视图" not in visible
    assert 'id="mappingMode" type="hidden"' in html
    assert 'id="mappingFloors" type="hidden"' in html
    for forbidden_id in (
        "spaceViewModeTag",
        "spaceViewFloor",
        "spaceViewLocalization",
        "spaceViewCloud",
        "spaceViewAsset",
    ):
        assert forbidden_id not in html, forbidden_id
    css = (STATIC / "dashboard.css").read_text(encoding="utf-8")
    assert "space-view-panel" not in html
    assert "space-view-panel" not in css
    assert "spaceViewCanvas" not in html
    assert html.index('id="teleopStatusBtn"') < html.index('id="batteryStatusBtn"')
    assert 'data-webrtc-path="video1/whep"' in html
    assert 'data-webrtc-path="video2/whep"' in html
    assert "startWebRtcVideoViewer" in script
    assert 'new RTCPeerConnection' in script
    assert "liveSyncDuration: 0.6" in script
    assert "latency > 2.0" in script
    assert "webrtc: yes" in camera_gateway
    assert "webrtcAddress: :8889" in camera_gateway
    assert "webrtcLocalUDPAddress: :8189" in camera_gateway
    assert "webrtcLocalTCPAddress: :8189" in camera_gateway
    assert "hlsSegmentDuration: 500ms" in camera_gateway
    camera_installer = (ROOT / "scripts/104_enable_camera_webrtc.sh").read_text(encoding="utf-8")
    assert "MediaMTX v1.20.0 or newer is required" in camera_installer
    assert 'id="mapCanvas" aria-label="三维点云地图视图"' in html
    assert 'if (status.state !== "running")' in script
    assert "三维建图运行包未安装，不能执行建图" in script
    assert "if (!error && !inProgress && payload && payload.session)" in script
    assert "A stale imported/cancelled session" in script
    assert "跨楼层编排" not in visible
    assert "空间连接维护" not in visible

    print("classic frontend contract tests passed")


if __name__ == "__main__":
    main()
