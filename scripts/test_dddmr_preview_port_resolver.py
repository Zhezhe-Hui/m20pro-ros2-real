#!/usr/bin/env python3
"""Behavioral checks for the shared DDDMR preview port resolver."""

import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
RESOLVER = ROOT / "scripts/104_resolve_dddmr_preview_port.sh"


def resolve(
    run_dir: Path,
    *,
    explicit_port: str = "",
    env_port: Optional[str] = None,
) -> str:
    env = os.environ.copy()
    env["M20PRO_DDDMR_PREVIEW_RUN_DIR"] = str(run_dir)
    if env_port is None:
        env.pop("M20PRO_DDDMR_PREVIEW_PORT", None)
    else:
        env["M20PRO_DDDMR_PREVIEW_PORT"] = env_port
    args = [str(RESOLVER)]
    if explicit_port:
        args.append(explicit_port)
    return subprocess.check_output(args, env=env, text=True).strip()


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)

        assert resolve(run_dir, env_port="19090") == "19090"
        assert resolve(run_dir, explicit_port="19191", env_port="19090") == "19191"
        assert resolve(run_dir) == "18080"

        live = subprocess.Popen(["sleep", "30"])
        try:
            live_pid_file = run_dir / "preview_19080.pid"
            live_pid_file.write_text(str(live.pid), encoding="utf-8")
            base_ts = time.time() - 10.0
            os.utime(live_pid_file, (base_ts, base_ts))

            stale_pid_file = run_dir / "preview_19081.pid"
            stale_pid_file.write_text("999999", encoding="utf-8")
            newer_ts = base_ts + 20.0
            os.utime(stale_pid_file, (newer_ts, newer_ts))

            assert resolve(run_dir) == "19080"
        finally:
            live.terminate()
            live.wait(timeout=5)

    print("DDDMR preview port resolver tests passed")


if __name__ == "__main__":
    main()
