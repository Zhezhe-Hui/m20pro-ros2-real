"""Compatibility re-export for the shared floor identity contract."""

from m20pro_navigation.floor_identity_contract import (  # noqa: F401
    augment_floor_config,
    configured_floor_ids,
    floor_level_from_id,
    normalize_floor_id,
    project_floor_ids,
    resolve_operational_floor,
    validate_floor_matches_map,
    validate_mapping_session_identity,
    validate_registered_floor,
    validate_runtime_map_floor,
)

__all__ = [
    "augment_floor_config",
    "configured_floor_ids",
    "floor_level_from_id",
    "normalize_floor_id",
    "project_floor_ids",
    "resolve_operational_floor",
    "validate_floor_matches_map",
    "validate_mapping_session_identity",
    "validate_registered_floor",
    "validate_runtime_map_floor",
]
