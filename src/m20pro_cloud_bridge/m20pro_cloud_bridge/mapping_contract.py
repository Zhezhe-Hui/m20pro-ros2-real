"""Pure mapping-session helpers for the web dashboard."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional


IdFactory = Callable[[str], str]
NowText = Callable[[], str]


def sanitize_mapping_name(value: str, fallback: str) -> str:
    text = str(value or "").strip() or str(fallback or "map")
    text = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", text)
    return text.strip("._") or str(fallback or "map")


def normalize_mapping_session_request(
    payload: Dict[str, Any],
    *,
    default_project_name: str,
    default_map_name: str,
) -> Dict[str, Any]:
    project_name = str(payload.get("project_name") or payload.get("name") or "").strip()
    building = str(payload.get("building") or "").strip()
    mode = str(payload.get("mode") or "multi").strip()
    floors_raw = payload.get("floors") or []
    if isinstance(floors_raw, str):
        floors_raw = [item.strip() for item in floors_raw.split(",") if item.strip()]
    floors = [str(item).strip() for item in floors_raw if str(item).strip()]
    active_floor = str(payload.get("active_floor") or (floors[0] if floors else "")).strip()
    fallback_name = default_map_name.format(active_floor=active_floor or "map")
    map_name = sanitize_mapping_name(str(payload.get("map_name") or ""), fallback_name)
    return {
        "project_name": project_name or str(default_project_name or "M20Pro 工地巡检"),
        "building": building,
        "mode": mode,
        "floors": floors,
        "active_floor": active_floor,
        "map_name": map_name,
    }


def find_mapping_project(projects: List[Dict[str, Any]], name: str, building: str) -> Optional[Dict[str, Any]]:
    for item in projects:
        if item.get("name") == name and item.get("building", "") == building:
            return item
    return None


def build_mapping_project_record(
    *,
    project_id: str,
    name: str,
    building: str,
    created_at: str,
    floors: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "id": str(project_id or ""),
        "name": str(name or ""),
        "building": str(building or ""),
        "floors": list(dict.fromkeys(str(item).strip() for item in (floors or []) if str(item).strip())),
        "created_at": str(created_at or ""),
    }


def register_mapping_project_floors(project: Dict[str, Any], floors: List[str]) -> Dict[str, Any]:
    updated = dict(project)
    registered = [str(item).strip() for item in (project.get("floors") or []) if str(item).strip()]
    for floor in floors:
        floor_id = str(floor or "").strip()
        if floor_id and floor_id not in registered:
            registered.append(floor_id)
    updated["floors"] = registered
    return updated


def build_mapping_session_record(
    *,
    session_id: str,
    project: Dict[str, Any],
    request: Dict[str, Any],
    created_at: str,
) -> Dict[str, Any]:
    floors = list(request.get("floors") or [])
    active_floor = str(request.get("active_floor") or "")
    base_map_name = str(request.get("map_name") or "")
    floor_steps = [
        {
            "floor": str(floor),
            "map_name": floor_map_name(base_map_name, active_floor, str(floor), len(floors) > 1),
            "status": "ready" if str(floor) == active_floor else "pending",
            "updated_at": str(created_at or ""),
        }
        for floor in floors
    ]
    return {
        "id": str(session_id or ""),
        "project_id": str(project.get("id") or ""),
        "project_name": str(request.get("project_name") or ""),
        "building": str(request.get("building") or ""),
        "mode": str(request.get("mode") or ""),
        "floors": floors,
        "active_floor": active_floor,
        "map_name": active_mapping_step(floor_steps, active_floor).get("map_name") or base_map_name,
        "floor_steps": floor_steps,
        "status": "created",
        "created_at": str(created_at or ""),
        "updated_at": str(created_at or ""),
    }


def floor_map_name(base_name: str, active_floor: str, floor: str, multi_floor: bool) -> str:
    base_name = sanitize_mapping_name(base_name, floor or "map")
    if not multi_floor:
        return base_name
    active_floor = str(active_floor or "").strip()
    floor = str(floor or "").strip()
    if active_floor and base_name.startswith(active_floor + "_"):
        return sanitize_mapping_name(floor + base_name[len(active_floor):], floor)
    if base_name.endswith("_" + active_floor) and active_floor:
        return sanitize_mapping_name(base_name[: -len(active_floor)] + floor, floor)
    return sanitize_mapping_name(f"{base_name}_{floor}", floor)


def active_mapping_step(steps: Any, active_floor: Any) -> Dict[str, Any]:
    floor = str(active_floor or "").strip()
    for item in steps if isinstance(steps, list) else []:
        if isinstance(item, dict) and str(item.get("floor") or "").strip() == floor:
            return item
    return {}


def mapping_floor_steps(session: Dict[str, Any]) -> List[Dict[str, Any]]:
    existing = session.get("floor_steps")
    if isinstance(existing, list) and existing:
        return [dict(item) for item in existing if isinstance(item, dict)]
    floors = [str(item).strip() for item in (session.get("floors") or []) if str(item).strip()]
    active_floor = str(session.get("active_floor") or "").strip()
    base_map_name = str(session.get("map_name") or "")
    return [
        {
            "floor": floor,
            "map_name": (
                sanitize_mapping_name(base_map_name, floor or "map")
                if floor == active_floor
                else floor_map_name(base_map_name, active_floor, floor, len(floors) > 1)
            ),
            "status": str(session.get("status") or "ready") if floor == active_floor else "pending",
            "updated_at": str(session.get("updated_at") or session.get("created_at") or ""),
        }
        for floor in floors
    ]


def select_mapping_floor(session: Dict[str, Any], floor: Any, *, updated_at: str) -> Dict[str, Any]:
    floor = str(floor or "").strip()
    steps = mapping_floor_steps(session)
    step = active_mapping_step(steps, floor)
    if not step:
        return {"ok": False, "code": "mapping_floor_missing", "message": "建图任务中没有该楼层"}
    if str(session.get("status") or "") == "mapping":
        return {"ok": False, "code": "mapping_floor_busy", "message": "当前楼层正在建图，完成或取消后才能切换步骤"}
    updated = dict(session)
    updated["floor_steps"] = steps
    updated["active_floor"] = floor
    updated["map_name"] = str(step.get("map_name") or "")
    updated["status"] = str(step.get("status") or "ready")
    updated["updated_at"] = str(updated_at or "")
    return {"ok": True, "session": updated, "step": step}


def prepare_mapping_session_create(
    payload: Dict[str, Any],
    *,
    projects: List[Dict[str, Any]],
    id_factory: IdFactory,
    now_text: NowText,
    default_project_name: str,
    default_map_name: str,
) -> Dict[str, Any]:
    request = normalize_mapping_session_request(
        payload,
        default_project_name=default_project_name,
        default_map_name=default_map_name,
    )
    project = find_mapping_project(projects, request["project_name"], request["building"])
    created_project = None
    updated_project = None
    if project is None:
        project = build_mapping_project_record(
            project_id=id_factory("project"),
            name=request["project_name"],
            building=request["building"],
            created_at=now_text(),
            floors=request["floors"],
        )
        created_project = project
    else:
        registered = register_mapping_project_floors(project, request["floors"])
        if registered != project:
            updated_project = registered
        project = registered
    session = build_mapping_session_record(
        session_id=id_factory("map_session"),
        project=project,
        request=request,
        created_at=now_text(),
    )
    return {
        "request": request,
        "project": project,
        "created_project": created_project,
        "updated_project": updated_project,
        "session": session,
    }


def mapping_command_status(param_name: str, current_status: Any, result: Dict[str, Any]) -> str:
    if result.get("ok"):
        return {
            "dddmr_mapping_start_command": "mapping",
            "dddmr_mapping_finish_command": "saved",
            "dddmr_mapping_cancel_command": "cancelled",
        }.get(str(param_name or ""), str(current_status or "updated"))
    if result.get("manual_required"):
        return "waiting_manual"
    if str(param_name or "") == "dddmr_mapping_finish_command":
        # A failed save is terminal for this capture. Keeping `mapping` here
        # makes a dead process look active after reboot and blocks new work.
        return "failed"
    return str(current_status or "updated")


def mapping_start_precondition(session: Dict[str, Any]) -> Dict[str, Any]:
    """Allow starting only a fresh/resumable session, never a terminal one."""
    status = str((session or {}).get("status") or "").strip()
    if status in ("mapping", "saving"):
        return {
            "ok": False,
            "code": "mapping_session_busy",
            "message": "该建图任务已经在进行中（含后台保存），请先完成或取消当前建图",
        }
    if status in ("saved", "imported", "cancelled", "failed"):
        return {
            "ok": False,
            "code": "mapping_session_terminal",
            "message": "该建图任务已经结束，请建立新的建图任务后再启动",
        }
    return {"ok": True, "status": status or "created"}


def recover_interrupted_mapping_sessions(
    sessions: List[Dict[str, Any]],
    *,
    mapping_status: Dict[str, Any],
    now_text: NowText,
) -> Dict[str, Any]:
    """Downgrade dead mapping sessions so startup cannot revive them."""
    state = str(mapping_status.get("state") or "").strip()
    if not (mapping_status.get("ok") is True and state not in ("running", "starting")):
        return {
            "changed": False,
            "sessions": [dict(item) for item in sessions if isinstance(item, dict)],
            "recovered_session_ids": [],
            "mapping_status": dict(mapping_status or {}),
        }

    updated_at = str(now_text() or "")
    mapper_died = state == "error"
    terminal_status = "failed" if mapper_died else "cancelled"
    terminal_message = (
        "三维建图进程已异常退出，当前采集无法保存，请重新创建建图任务"
        if mapper_died
        else "三维建图服务已重启或退出，当前会话已自动取消，请重新创建建图任务"
    )
    failure_code = (
        str(mapping_status.get("code") or "mapping_process_died")
        if mapper_died
        else "mapping_interrupted_restart"
    )
    recovered_session_ids: List[str] = []
    normalized_sessions: List[Dict[str, Any]] = []
    save_job_state = str(mapping_status.get("save_job_state") or "").strip()
    for item in sessions:
        if not isinstance(item, dict):
            continue
        session = dict(item)
        # saving 是 2026-08-21 引入的后台保存中间态: 服务重启后后台 job 必然
        # 丢失, 与 mapping 一样必须降级, 否则会话永远卡在"保存中"。
        # 但保存 job 仍在运行时(后台归档中), 建图进程本就应当已经退出——
        # 此时把 saving 会话误判为"中断"会把成功保存覆盖成取消
        # (2026-08-31 实测: 保存完成资产已注册, 会话仍被标成已取消)。
        session_status = str(session.get("status") or "").strip()
        if session_status == "saving" and save_job_state == "running":
            normalized_sessions.append(session)
            continue
        if session_status in ("mapping", "saving"):
            session["status"] = terminal_status
            session["status_message"] = terminal_message
            session["failure_code"] = failure_code
            session["updated_at"] = updated_at
            steps = mapping_floor_steps(session)
            active_floor = str(session.get("active_floor") or "").strip()
            step = active_mapping_step(steps, active_floor)
            if step:
                step["status"] = terminal_status
                step["updated_at"] = updated_at
            session["floor_steps"] = steps
            recovered_session_ids.append(str(session.get("id") or "").strip())
        normalized_sessions.append(session)
    return {
        "changed": bool(recovered_session_ids),
        "sessions": normalized_sessions,
        "recovered_session_ids": recovered_session_ids,
        "mapping_status": dict(mapping_status or {}),
    }


def mapping_runtime_precondition(param_name: str, status: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a live DDDMR mapping status before start or finish."""
    if param_name not in ("dddmr_mapping_start_command", "dddmr_mapping_finish_command"):
        return {"ok": True}
    if status.get("configured") is not True:
        return {
            "ok": False,
            "code": "dddmr_mapping_status_unconfigured",
            "message": "三维建图运行时状态命令未配置，不能执行建图",
        }
    if status.get("ok") is not True:
        return {
            "ok": False,
            "code": str(status.get("code") or "dddmr_mapping_status_failed"),
            "message": "三维建图运行时状态读取失败，不能执行建图",
        }
    if status.get("package_available") is not True:
        return {
            "ok": False,
            "code": str(status.get("code") or "dddmr_runtime_missing"),
            "message": "三维建图 Humble 运行包未安装或未 source，不能执行建图",
        }
    if status.get("mapping_launch_available") is not True:
        return {
            "ok": False,
            "code": str(status.get("code") or "dddmr_mapping_launch_missing"),
            "message": "三维建图启动包未从当前 M20Pro 工作区加载，不能执行建图",
        }
    # source_cloud_available is intentionally NOT a hard start precondition:
    # the start command self-heals an expired/hung dense chain unattended
    # (ensure_source_cloud_chain in 104_dddmr_mapping_control.sh, 2026-08-19).
    # Blocking here would prevent the recovery from ever running and strand
    # the operator with a manual shell step. The start command's own gate
    # stays the arbiter: when self-heal fails it exits 25 with
    # code=lightning_source_cloud_missing and a message, which the Web node
    # surfaces to the frontend.

    state = str(status.get("state") or "").strip()
    if param_name == "dddmr_mapping_start_command" and state == "running":
        return {
            "ok": False,
            "code": "dddmr_mapping_busy",
            "message": "三维建图已经在运行，请先结束或取消当前建图",
        }
    if param_name == "dddmr_mapping_finish_command":
        if state == "starting":
            return {
                "ok": False,
                "code": "dddmr_mapping_starting",
                "message": "三维建图正在启动，请稍候几秒再点保存",
            }
        if state == "error":
            status_code = str(status.get("code") or "")
            status_message = str(status.get("message") or "")
            if "diverge" in status_code:
                return {
                    "ok": False,
                    "code": "lightning_diverged",
                    "message": status_message
                    or "三维建图定位已发散，后台建图已停止，本次地图无法保存；请重新开始建图",
                }
            return {
                "ok": False,
                "code": status_code or "dddmr_mapping_error",
                "message": status_message
                or "三维建图进程已异常退出，本次采集无法保存；请重新开始建图",
            }
        if state != "running":
            return {
                "ok": False,
                "code": "dddmr_mapping_not_running",
                "message": "三维建图当前未运行，不能结束并保存建图",
            }
        if status.get("save_service_available") is not True:
            return {
                "ok": False,
                "code": "dddmr_save_service_missing",
                "message": "三维建图保存服务不可用，不能结束并保存建图",
            }
    return {"ok": True}


def mapping_environment_precondition(
    command_templates: Dict[str, Any],
    status: Dict[str, Any],
) -> Dict[str, Any]:
    """Require every control command and a usable idle/running DDDMR runtime."""
    required = ("start", "finish", "cancel", "status")
    missing = [name for name in required if not str(command_templates.get(name) or "").strip()]
    if missing:
        return {
            "ok": False,
            "code": "dddmr_mapping_commands_unconfigured",
            "message": "三维建图环境未通过：请先配置全部建图命令模板。",
            "missing_commands": missing,
        }
    runtime = mapping_runtime_precondition("dddmr_mapping_start_command", status)
    if not runtime.get("ok") and runtime.get("code") != "dddmr_mapping_busy":
        return runtime
    return {
        "ok": True,
        "message": "三维建图环境可用：命令模板、状态查询和运行包均已就绪。",
    }


def apply_mapping_command_result(
    session: Dict[str, Any],
    *,
    param_name: str,
    result: Dict[str, Any],
    updated_at: str,
) -> Dict[str, Any]:
    updated = dict(session)
    updated["status"] = mapping_command_status(param_name, session.get("status"), result)
    updated["updated_at"] = str(updated_at or "")
    steps = mapping_floor_steps(session)
    step = active_mapping_step(steps, session.get("active_floor"))
    if step:
        step["status"] = updated["status"]
        step["updated_at"] = str(updated_at or "")
        updated["floor_steps"] = steps
    return updated


def mark_mapping_floor_imported(
    session: Dict[str, Any],
    *,
    floor: str,
    map_id: str,
    updated_at: str,
) -> Dict[str, Any]:
    updated = dict(session)
    steps = mapping_floor_steps(session)
    step = active_mapping_step(steps, floor)
    if step:
        step["status"] = "imported"
        step["map_id"] = str(map_id or "")
        step["updated_at"] = str(updated_at or "")
    updated["floor_steps"] = steps
    updated["active_floor"] = str(floor or "")
    updated["map_name"] = str(step.get("map_name") or updated.get("map_name") or "")
    updated["status"] = "imported"
    updated["updated_at"] = str(updated_at or "")
    return updated


def mapping_finish_asset_registration_payload(
    session: Dict[str, Any],
    result: Dict[str, Any],
    *,
    source: str,
    updated_at: str,
) -> Dict[str, Any]:
    """Build the 3D map-asset registration payload from a finished mapping run."""

    if result.get("ok") is not True:
        return {}
    floor = str(session.get("active_floor") or result.get("floor") or "").strip()
    if not floor:
        return {}
    archive_target = str(result.get("archive_target") or "").strip()

    def result_path(key: str, fallback_name: str) -> str:
        value = str(result.get(key) or "").strip()
        if not value and archive_target:
            value = f"{archive_target.rstrip('/')}/{fallback_name}"
        return value

    mapcloud = result_path("mapcloud", "map.pcd")
    mapground = result_path("mapground", "ground.pcd")
    if not mapcloud or not mapground:
        return {}

    step = active_mapping_step(mapping_floor_steps(session), floor)
    label = sanitize_mapping_name(
        str(step.get("map_name") or session.get("map_name") or result.get("map_id") or floor),
        floor,
    )
    payload: Dict[str, Any] = {
        "floor": floor,
        "label": label,
        "source": str(source or "").strip(),
        "mapcloud": [mapcloud],
        "mapground": [mapground],
        "updated_at": str(updated_at or ""),
    }
    note_parts = []
    if str(session.get("project_name") or "").strip():
        note_parts.append(f"project={str(session.get('project_name') or '').strip()}")
    if str(session.get("building") or "").strip():
        note_parts.append(f"building={str(session.get('building') or '').strip()}")
    if archive_target:
        note_parts.append(f"archive={archive_target}")
        payload["archive_target"] = archive_target
    for key in ("map_id", "saved_dir", "poses", "pose_graph_dir", "backend", "save_log", "asset_log"):
        value = str(result.get(key) or "").strip()
        if value:
            payload[key] = value
    if "pose_graph_dir" not in payload and archive_target:
        payload["pose_graph_dir"] = archive_target
    if note_parts:
        payload["note"] = "; ".join(note_parts)
    return payload


def mapping_command_context(
    session: Dict[str, Any],
    *,
    factory_host: str,
    factory_user: str,
    factory_active_map: str,
    map_archive_dir: str,
) -> Dict[str, str]:
    step = active_mapping_step(mapping_floor_steps(session), session.get("active_floor"))
    return {
        "session_id": str(session.get("id", "")),
        "project_name": str(session.get("project_name", "")),
        "building": str(session.get("building", "")),
        "mode": str(session.get("mode", "")),
        "active_floor": str(session.get("active_floor", "")),
        "map_name": sanitize_mapping_name(
            str(step.get("map_name") or session.get("map_name") or ""),
            str(session.get("id", "map")),
        ),
        "floors": ",".join(str(item) for item in session.get("floors") or []),
        "factory_host": str(factory_host or ""),
        "factory_user": str(factory_user or ""),
        "factory_active_map": str(factory_active_map or ""),
        "map_archive_dir": str(map_archive_dir or ""),
    }
