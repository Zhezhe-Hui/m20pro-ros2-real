"""Pure contracts for the optional DDDMR 3D map asset manifest."""

from __future__ import annotations

import math
import hashlib
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .floor_identity_contract import normalize_floor_id


DDDMR_MAP_ASSET_SCHEMA_VERSION = 1


def _path_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = value.replace("\n", ",").split(",")
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, dict)):
        values = list(value)
    else:
        values = [value]
    result: List[str] = []
    for item in values:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _asset_slug(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", text)
    return text.strip("._") or "asset"


def dddmr_map_asset_id(record: Mapping[str, Any]) -> str:
    explicit = str(record.get("asset_id") or record.get("id") or "").strip()
    if explicit:
        return _asset_slug(explicit)
    floor = _asset_slug(record.get("floor") or "floor")
    label = _asset_slug(record.get("label") or record.get("name") or floor)
    fingerprint_source = "|".join(
        [
            floor,
            label,
            ",".join(_path_list(record.get("mapcloud"))),
            ",".join(_path_list(record.get("mapground"))),
            str(record.get("pose_graph_dir") or ""),
            str(record.get("archive_target") or ""),
        ]
    )
    digest = hashlib.sha1(fingerprint_source.encode("utf-8")).hexdigest()[:12]
    return _asset_slug(f"{floor}_{label}_{digest}")


def normalize_dddmr_map_asset_record(
    floor: Any,
    record: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    payload = dict(record or {})
    floor_id = normalize_floor_id(floor or payload.get("floor"))
    if not floor_id:
        floor_id = str(floor or payload.get("floor") or "").strip()
    if not floor_id:
        raise ValueError("dddmr_map_floor_invalid")
    cloud = _path_list(
        payload.get("mapcloud")
        or payload.get("mapcloud_files")
        or payload.get("cloud")
    )
    ground = _path_list(
        payload.get("mapground")
        or payload.get("mapground_files")
        or payload.get("ground")
    )
    normalized = dict(payload)
    normalized["floor"] = floor_id
    normalized["mapcloud"] = cloud
    normalized["mapground"] = ground
    label = str(payload.get("label") or payload.get("name") or "").strip()
    normalized["label"] = label or floor_id
    normalized["asset_id"] = dddmr_map_asset_id(normalized)
    return normalized


def validate_dddmr_map_asset_registration(
    payload: Mapping[str, Any],
) -> Dict[str, Any]:
    try:
        record = normalize_dddmr_map_asset_record(payload.get("floor"), payload)
    except ValueError:
        return {
            "ok": False,
            "code": "dddmr_map_floor_invalid",
            "message": "DDDMR 3D 资产楼层格式无效",
        }
    cloud = list(record.get("mapcloud") or [])
    ground = list(record.get("mapground") or [])
    if not cloud:
        return {
            "ok": False,
            "code": "dddmr_mapcloud_missing",
            "message": "请至少填写一个 mapcloud 资产路径",
            "floor": record["floor"],
        }
    if not ground:
        return {
            "ok": False,
            "code": "dddmr_mapground_missing",
            "message": "请至少填写一个 mapground 资产路径",
            "floor": record["floor"],
        }
    record["note"] = str(payload.get("note") or payload.get("description") or "").strip()
    record["source"] = str(payload.get("source") or payload.get("mapping_source") or "").strip()
    if payload.get("updated_at") is not None:
        record["updated_at"] = str(payload.get("updated_at") or "").strip()
    return {
        "ok": True,
        "record": record,
        "floor": record["floor"],
        "mapcloud": cloud,
        "mapground": ground,
    }


def normalize_dddmr_map_asset_manifest(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {"schema_version": DDDMR_MAP_ASSET_SCHEMA_VERSION, "floors": {}, "assets": {}}
    normalized = dict(raw)
    try:
        normalized["schema_version"] = int(
            normalized.get("schema_version") or DDDMR_MAP_ASSET_SCHEMA_VERSION
        )
    except (TypeError, ValueError):
        normalized["schema_version"] = DDDMR_MAP_ASSET_SCHEMA_VERSION
    floors = normalized.get("floors")
    floor_records: Dict[str, Any] = {}
    if isinstance(floors, dict):
        for floor, record in floors.items():
            try:
                normalized_record = normalize_dddmr_map_asset_record(floor, record)
            except ValueError:
                continue
            floor_records[str(normalized_record["floor"])] = normalized_record
    normalized["floors"] = floor_records
    asset_records: Dict[str, Any] = {}
    raw_assets = normalized.get("assets") or normalized.get("asset_library") or {}
    if isinstance(raw_assets, dict):
        asset_iterable = raw_assets.items()
    elif isinstance(raw_assets, list):
        asset_iterable = [(None, item) for item in raw_assets]
    else:
        asset_iterable = []
    for asset_key, record in asset_iterable:
        if not isinstance(record, Mapping):
            continue
        payload = dict(record)
        if asset_key is not None and not str(payload.get("asset_id") or payload.get("id") or "").strip():
            payload["asset_id"] = str(asset_key)
        try:
            normalized_record = normalize_dddmr_map_asset_record(payload.get("floor"), payload)
        except ValueError:
            continue
        asset_records[str(normalized_record["asset_id"])] = normalized_record
    for record in floor_records.values():
        asset_records.setdefault(str(record["asset_id"]), dict(record))
    normalized["assets"] = asset_records
    return normalized


def upsert_dddmr_map_asset(
    manifest: Mapping[str, Any],
    record: Mapping[str, Any],
) -> Dict[str, Any]:
    updated = normalize_dddmr_map_asset_manifest(dict(manifest or {}))
    normalized = normalize_dddmr_map_asset_record(record.get("floor"), record)
    updated.setdefault("schema_version", DDDMR_MAP_ASSET_SCHEMA_VERSION)
    floors = dict(updated.get("floors") or {})
    floors[str(normalized["floor"])] = normalized
    updated["floors"] = floors
    assets = dict(updated.get("assets") or {})
    assets[str(normalized["asset_id"])] = normalized
    updated["assets"] = assets
    return updated


def remove_dddmr_map_asset(manifest: Mapping[str, Any], floor: Any) -> Dict[str, Any]:
    updated = normalize_dddmr_map_asset_manifest(dict(manifest or {}))
    floor_id = normalize_floor_id(floor) or str(floor or "").strip()
    floors = dict(updated.get("floors") or {})
    if floor_id:
        floors.pop(floor_id, None)
    updated["floors"] = floors
    return updated


def remove_dddmr_map_asset_record(manifest: Mapping[str, Any], asset_id: Any) -> Dict[str, Any]:
    """Remove one 3D map asset from the library and unlink active floors using it."""

    updated = normalize_dddmr_map_asset_manifest(dict(manifest or {}))
    target_id = str(asset_id or "").strip()
    if not target_id:
        return {
            "ok": False,
            "code": "dddmr_map_asset_id_missing",
            "message": "请指定要删除的三维地图资产",
            "manifest": updated,
        }

    assets = dict(updated.get("assets") or {})
    record = assets.pop(target_id, None)
    if record is None:
        for candidate_id, candidate in list(assets.items()):
            if not isinstance(candidate, Mapping):
                continue
            if str(candidate.get("asset_id") or candidate.get("id") or "").strip() == target_id:
                record = assets.pop(candidate_id, None)
                target_id = str(candidate_id)
                break
    if record is None:
        return {
            "ok": False,
            "code": "dddmr_map_asset_not_found",
            "message": "三维地图资产不存在",
            "manifest": updated,
            "asset_id": target_id,
        }

    floors = dict(updated.get("floors") or {})
    removed_floors: List[str] = []
    for floor, floor_record in list(floors.items()):
        if not isinstance(floor_record, Mapping):
            continue
        if str(floor_record.get("asset_id") or "").strip() == target_id:
            removed_floors.append(str(floor))
            floors.pop(floor, None)

    updated["assets"] = assets
    updated["floors"] = floors
    return {
        "ok": True,
        "code": "dddmr_map_asset_removed",
        "message": "三维地图资产已删除",
        "manifest": updated,
        "asset_id": target_id,
        "record": dict(record),
        "removed_floors": removed_floors,
    }


def dddmr_map_asset_workspace(manifest: Mapping[str, Any]) -> Dict[str, Any]:
    normalized = normalize_dddmr_map_asset_manifest(dict(manifest or {}))
    floors = normalized.get("floors") if isinstance(normalized.get("floors"), dict) else {}
    assets = normalized.get("assets") if isinstance(normalized.get("assets"), dict) else {}
    active_asset_ids = {
        str(record.get("asset_id") or "")
        for record in floors.values()
        if isinstance(record, Mapping) and str(record.get("asset_id") or "")
    }
    records = []
    for floor, record in floors.items():
        cloud = list(record.get("mapcloud") or [])
        ground = list(record.get("mapground") or [])
        records.append(
            {
                "floor": str(floor),
                "asset_id": str(record.get("asset_id") or ""),
                "label": str(record.get("label") or floor),
                "note": str(record.get("note") or "").strip(),
                "source": str(record.get("source") or "").strip(),
                "mapcloud": cloud,
                "mapground": ground,
                "mapcloud_count": len(cloud),
                "mapground_count": len(ground),
                "ready": bool(cloud and ground),
                "active": True,
                "updated_at": str(record.get("updated_at") or "").strip(),
            }
        )
    records.sort(key=lambda item: item["floor"])
    asset_items = []
    for asset_id, record in assets.items():
        if not isinstance(record, Mapping):
            continue
        cloud = list(record.get("mapcloud") or [])
        ground = list(record.get("mapground") or [])
        asset_items.append(
            {
                "asset_id": str(record.get("asset_id") or asset_id),
                "floor": str(record.get("floor") or ""),
                "label": str(record.get("label") or record.get("floor") or asset_id),
                "note": str(record.get("note") or "").strip(),
                "source": str(record.get("source") or "").strip(),
                "mapcloud": cloud,
                "mapground": ground,
                "mapcloud_count": len(cloud),
                "mapground_count": len(ground),
                "ready": bool(cloud and ground),
                "active": str(record.get("asset_id") or asset_id) in active_asset_ids,
                "updated_at": str(record.get("updated_at") or "").strip(),
                "archive_target": str(record.get("archive_target") or "").strip(),
                "pose_graph_dir": str(record.get("pose_graph_dir") or "").strip(),
                "poses": str(record.get("poses") or "").strip(),
            }
        )
    asset_items.sort(key=lambda item: (item["floor"], item["label"], item["asset_id"]))
    return {
        "schema_version": int(normalized.get("schema_version") or DDDMR_MAP_ASSET_SCHEMA_VERSION),
        "floor_count": len(records),
        "ready_floor_count": sum(1 for item in records if item["ready"]),
        "floors": records,
        "asset_count": len(asset_items),
        "ready_asset_count": sum(1 for item in asset_items if item["ready"]),
        "assets": asset_items,
    }


def generate_dddmr_field_test_flat_map_points(
    *,
    extent_m: float = 2.0,
    spacing_m: float = 0.25,
    height_m: float = 0.0,
) -> List[Tuple[float, float, float]]:
    extent = float(extent_m)
    spacing = float(spacing_m)
    height = float(height_m)
    if not math.isfinite(extent) or extent <= 0.0:
        raise ValueError("field_test_flat_map_extent_invalid")
    if not math.isfinite(spacing) or spacing <= 0.0:
        raise ValueError("field_test_flat_map_spacing_invalid")
    if not math.isfinite(height):
        raise ValueError("field_test_flat_map_height_invalid")
    steps = max(1, int(round(extent / spacing)))
    points = []
    for xi in range(-steps, steps + 1):
        x = round(xi * spacing, 6)
        for yi in range(-steps, steps + 1):
            y = round(yi * spacing, 6)
            points.append((x, y, height))
    return points


__all__ = [
    "DDDMR_MAP_ASSET_SCHEMA_VERSION",
    "dddmr_map_asset_id",
    "dddmr_map_asset_workspace",
    "normalize_dddmr_map_asset_manifest",
    "normalize_dddmr_map_asset_record",
    "remove_dddmr_map_asset",
    "upsert_dddmr_map_asset",
    "validate_dddmr_map_asset_registration",
    "generate_dddmr_field_test_flat_map_points",
]
