#!/usr/bin/env python3
"""Static contract checks for the Lightning ESKF safety invariants."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "vendor/lightning_lm_deep_robotics/src/core/lio/eskf.cc"


def require(text: str, fragment: str, message: str) -> None:
    if fragment not in text:
        raise AssertionError(f"{message}: missing {fragment!r}")


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    require(text, "bool LimitNorm(Block&& block", "correction limits must update the state vector")
    require(text, "dt <= 0.0", "prediction must reject non-forward time")
    require(text, "!Q.allFinite()", "prediction must reject invalid process noise")
    require(text, "if (!f_.allFinite() || !f_x_.allFinite() || !f_w_.allFinite())", "prediction must reject invalid dynamics")
    require(text, "x_ = state_before;\n        P_ = covariance_before;", "invalid prediction must roll back state and covariance")
    require(text, "Eigen::LDLT<Eigen::MatrixXd> innovation_solver", "innovation solve must avoid explicit inverse")
    require(text, "Eigen::LDLT<CovType> covariance_solver", "covariance solve must avoid explicit inverse")
    print("lightning ESKF safety contract: ok")


if __name__ == "__main__":
    main()
