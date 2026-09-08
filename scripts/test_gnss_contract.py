#!/usr/bin/env python3
"""Contract tests for M20Pro GNSS normalization."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/m20pro_navigation"))

from m20pro_navigation.gnss_contract import (  # noqa: E402
    GNSS_FIX_TOPIC,
    GNSS_SOURCE_TOPIC,
    covariance_from_dop,
    gnss_quality_status,
    normalize_gnss_sample,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError("%s: expected %r, got %r" % (message, expected, actual))


def assert_true(value, message: str) -> None:
    if not value:
        raise AssertionError(message)


def test_normalizes_factory_ros_message_shape() -> None:
    class Value:
        latitude = 30.123456
        longitude = 120.123456
        speed = 0.5
        course = 180.0
        fixquality = 1
        numsatellites = 12
        altitude = 15.3
        pdop = 1.8
        hdop = 1.2
        vdop = 1.5
        totalmessages = 1
        currentmessage = 1
        visiblesatellites = 18

    class Message:
        data = Value()

    sample = normalize_gnss_sample(Message(), received_at=123.0)
    assert_true(sample["fix_valid"], "valid fix accepted")
    assert_equal(sample["latitude"], 30.123456, "latitude")
    assert_equal(sample["longitude"], 120.123456, "longitude")
    assert_equal(sample["altitude_m"], 15.3, "altitude")
    assert_equal(sample["speed_kmh"], 0.5, "speed")
    assert_equal(sample["course_deg"], 180.0, "course")
    assert_equal(sample["num_satellites"], 12, "satellites")
    assert_equal(sample["visible_satellites"], 18, "visible satellites")
    assert_equal(sample["pdop"], 1.8, "pdop")
    assert_equal(sample["vdop"], 1.5, "vdop")
    assert_equal(sample["received_at"], 123.0, "received time")


def test_normalizes_basic_server_shape() -> None:
    sample = normalize_gnss_sample(
        {
            "Latitude": 30.1,
            "Longitude": 120.2,
            "Speed": 1.0,
            "Course": 12.0,
            "FixQuality": 1,
            "NumSatellites": 8,
            "Altitude": 16.0,
            "HDOP": 1.5,
        }
    )
    assert_true(sample["fix_valid"], "basic_server GPS fix accepted")
    assert_equal(sample["speed_kmh"], 1.0, "speed")
    assert_equal(sample["hdop"], 1.5, "hdop")


def test_normalizes_nested_gps_group_shape() -> None:
    sample = normalize_gnss_sample(
        {
            "GPS": {
                "Latitude": 30.2,
                "Longitude": 120.3,
                "Speed": 0.8,
                "Course": 91.0,
                "FixQuality": 1,
                "NumSatellites": 10,
                "Altitude": 18.5,
                "HDOP": 1.1,
                "VDOP": 1.7,
                "VisibleSatellites": 16,
            }
        }
    )
    assert_true(sample["fix_valid"], "nested GPS group accepted")
    assert_equal(sample["latitude"], 30.2, "nested latitude")
    assert_equal(sample["longitude"], 120.3, "nested longitude")
    assert_equal(sample["visible_satellites"], 16, "nested visible satellites")


def test_normalizes_items_wrapped_gps_group_shape() -> None:
    sample = normalize_gnss_sample(
        {
            "Items": [
                {"BatteryStatus": {"Voltage": 12.5}},
                {
                    "GPS": {
                        "Latitude": 30.4,
                        "Longitude": 120.5,
                        "FixQuality": 1,
                        "NumSatellites": 9,
                        "HDOP": 1.4,
                    }
                },
            ]
        }
    )
    assert_true(sample["fix_valid"], "items-wrapped GPS group accepted")
    assert_equal(sample["latitude"], 30.4, "items latitude")
    assert_equal(sample["longitude"], 120.5, "items longitude")


def test_quality_gate_is_conservative() -> None:
    sample = normalize_gnss_sample(
        {
            "Latitude": 30.1,
            "Longitude": 120.2,
            "FixQuality": 1,
            "NumSatellites": 8,
            "HDOP": 1.5,
        }
    )
    ok = gnss_quality_status(sample, age_s=0.1, max_hdop=2.5, min_satellites=6)
    assert_true(ok["ready"], "good GNSS sample is anchor usable")
    assert_equal(ok["code"], "gnss_anchor_ready", "good code")
    assert_equal(ok["used_for_motion"], False, "GNSS does not authorize motion")
    assert_equal(ok["source_topic"], GNSS_SOURCE_TOPIC, "GNSS source topic")
    assert_equal(ok["fix_topic"], GNSS_FIX_TOPIC, "GNSS fix topic")

    no_fix = dict(sample, fix_quality=0, fix_valid=False)
    assert_equal(
        gnss_quality_status(no_fix, age_s=0.1)["code"],
        "gnss_no_fix",
        "no-fix code",
    )
    low_sat = dict(sample, num_satellites=3)
    assert_equal(
        gnss_quality_status(low_sat, age_s=0.1, min_satellites=6)["code"],
        "gnss_satellites_low",
        "low satellites code",
    )
    high_hdop = dict(sample, hdop=5.0)
    assert_equal(
        gnss_quality_status(high_hdop, age_s=0.1, max_hdop=2.5)["code"],
        "gnss_hdop_high",
        "high HDOP code",
    )
    stale = gnss_quality_status(sample, age_s=5.0, timeout_s=3.0)
    assert_equal(stale["code"], "gnss_stale", "stale code")
    disabled = gnss_quality_status(sample, enabled=False)
    assert_equal(disabled["code"], "gnss_adapter_disabled", "disabled code")
    assert_true(disabled["ready"] is False, "disabled GNSS not ready")


def test_covariance_from_dop() -> None:
    estimated = covariance_from_dop(hdop=1.2, vdop=1.5, uere_m=4.0)
    assert_equal(estimated["type"], 1, "approximated covariance type")
    assert_true(estimated["covariance"][0] > 0.0, "horizontal variance")
    assert_true(estimated["covariance"][8] > estimated["covariance"][0], "vertical variance")
    unknown = covariance_from_dop(hdop=None, vdop=None)
    assert_equal(unknown["type"], 0, "unknown covariance type")


if __name__ == "__main__":
    test_normalizes_factory_ros_message_shape()
    test_normalizes_basic_server_shape()
    test_normalizes_nested_gps_group_shape()
    test_normalizes_items_wrapped_gps_group_shape()
    test_quality_gate_is_conservative()
    test_covariance_from_dop()
    print("GNSS contract tests passed")
