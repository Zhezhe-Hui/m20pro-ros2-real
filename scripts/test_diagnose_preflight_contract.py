#!/usr/bin/env python3
"""Source contract checks for the 104 read-only diagnosis entrypoint."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    diagnose = (ROOT / "scripts" / "104_diagnose_preflight.sh").read_text(
        encoding="utf-8"
    )
    readme = (ROOT / "scripts" / "README.md").read_text(encoding="utf-8")

    assert "navigation_backend_summary.py" in diagnose
    assert "NAVIGATION_SUMMARY_HELPER" in diagnose
    assert "summarize_navigation_state" in diagnose
    assert "navigation_backend_summary=" in diagnose
    assert "M20PRO_NAVIGATION_SUMMARY_HELPER=" not in diagnose
    assert "read-only; it does not publish cmd_vel" in diagnose
    assert "/api/state" in diagnose
    assert "/api/preflight/run" in diagnose
    assert "104_diagnose_preflight.sh" in readme
    assert "DDDMR" in readme
    assert "GNSS" in readme
    print("diagnose preflight contract tests passed")


if __name__ == "__main__":
    main()
