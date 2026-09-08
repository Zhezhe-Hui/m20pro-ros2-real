#!/usr/bin/env python3
"""Contract checks for the 104 status scripts."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    status = (ROOT / "scripts" / "104_status.sh").read_text(encoding="utf-8")
    autostart = (ROOT / "scripts" / "104_autostart_status.sh").read_text(encoding="utf-8")

    for text in (status, autostart):
        assert "navigation_backend_summary.py" in text
        assert 'SUMMARY_JSON="${summary_json}" python3 - <<\'PY\'' in text
        assert "field_test_mode: current=%s label=%s available=%s motion_enabled=%s acceptance=%s reason=%s" in text
        assert "gnss: ready=%s source=%s fix=%s anchor=%s code=%s" in text
        assert "command_mux: seen=%s mode=%s output_nonzero=%s stale=%s age_s=%s reason=%s" in text
        assert 'gnss.get("source_topic") or "/GPS"' in text
        assert 'gnss.get("fix_topic") or "/m20pro/gnss/fix"' in text
        assert "current_motion_enabled" in text
        assert "acceptance.get(\"ready\")" in text
        assert "command_mux.get(\"age_s\")" in text

    print("104 status contract tests passed")


if __name__ == "__main__":
    main()
