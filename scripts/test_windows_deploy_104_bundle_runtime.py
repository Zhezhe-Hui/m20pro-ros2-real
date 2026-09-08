#!/usr/bin/env python3
"""Runtime smoke for the Windows PowerShell 104 deployment entrypoint."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def _run_powershell(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "windows_deploy_104_bundle.ps1"),
            *args,
        ],
        cwd=str(ROOT),
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )


def main() -> int:
    result = _run_powershell("-DryRun", "-RestartEdge106", "-RequireFieldReady")
    output = result.stdout or ""
    if result.returncode != 0:
        raise AssertionError(f"PowerShell dry-run failed: {result.returncode}\n{output}")

    assert_true("[windows_deploy_104_bundle] DRY RUN" in output, "dry-run marker missing")
    assert_true("restart_edge_106=True" in output, "edge restart flag missing")
    assert_true("ssh -tt user@10.21.31.104" in output, "104 ssh command missing")
    assert_true("ssh -tt user@10.21.31.106" in output, "106 ssh command missing")
    assert_true("windows_deploy_104_bundle" in output, "script banner missing")

    stage_match = re.search(r"stage=([^\r\n]+)", output)
    runner_match = re.search(r"runner=([^\r\n]+)", output)
    revision_match = re.search(r"revision=([^\r\n]+)", output)
    assert_true(stage_match is not None, "stage path missing")
    assert_true(runner_match is not None, "runner path missing")
    assert_true(revision_match is not None, "revision missing")
    stage_path = stage_match.group(1).strip()
    runner_path = runner_match.group(1).strip()
    expected_revision = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    ).stdout.strip()
    if dirty:
        expected_revision += "-worktree"
    assert_true(revision_match.group(1).strip() == expected_revision, "revision not sourced from bundle")

    cleanup = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            (
                f"if ((Test-Path -LiteralPath '{stage_path}') -or "
                f"(Test-Path -LiteralPath '{runner_path}')) {{ exit 1 }} "
                "else { exit 0 }"
            ),
        ],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
        check=False,
    )
    if cleanup.returncode != 0:
        raise AssertionError(
            "temporary PowerShell staging files were not cleaned up\n"
            f"stage={stage_path}\nrunner={runner_path}\n{cleanup.stdout}"
        )

    print("[OK] Windows PowerShell 104 deployment runtime smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
