"""Pure helpers for MLServer output parsing + counting."""

from datetime import UTC, datetime

from city_pulse.workers.inference import (
    count_vehicle_detections,
    count_vehicle_detections_advanced,
    parse_bboxes,
    parse_infer_outputs,
    parse_norm_roi,
    vehicle_label_allowlist,
)


def test_vehicle_label_allowlist() -> None:
    assert vehicle_label_allowlist("car, truck") == {"car", "truck"}


def test_count_respects_confidence_and_allowlist() -> None:
    allowed = {"car", "bus"}
    assert (
        count_vehicle_detections(
            ["car", "person", "bus"],
            [0.9, 0.99, 0.1],
            allowed=allowed,
            min_confidence=0.25,
        )
        == 1
    )


def test_parse_infer_outputs_mixed() -> None:
    body = {
        "outputs": [
            {"name": "bboxes", "data": []},
            {
                "name": "labels",
                "data": ["car", "kite"],
            },
            {"name": "scores", "data": [0.8, 0.2]},
        ]
    }
    labels, scores = parse_infer_outputs(body)
    assert labels == ["car", "kite"]
    assert scores == [0.8, 0.2]


def test_parse_bboxes_nested_and_flat() -> None:
    body_nested = {
        "outputs": [{"name": "bboxes", "data": [[1, 2, 3, 4], [5, 6, 7, 8]]}]
    }
    assert parse_bboxes(body_nested) == [
        (1.0, 2.0, 3.0, 4.0),
        (5.0, 6.0, 7.0, 8.0),
    ]

    body_flat = {"outputs": [{"name": "boxes", "data": [9, 10, 11, 12]}]}
    assert parse_bboxes(body_flat) == [(9.0, 10.0, 11.0, 12.0)]


def test_parse_norm_roi_valid_and_invalid() -> None:
    assert parse_norm_roi("0.1,0.2,0.9,1.0") == (0.1, 0.2, 0.9, 1.0)
    assert parse_norm_roi("0.1,0.2,0.1,1.0") is None
    assert parse_norm_roi("abc") is None


def test_advanced_count_roi_and_dedup() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    count, recent = count_vehicle_detections_advanced(
        labels=["car", "car", "truck"],
        scores=[0.8, 0.7, 0.8],
        bboxes=[
            (500.0, 100.0, 560.0, 170.0),  # inside ROI
            (502.0, 102.0, 562.0, 172.0),  # almost same car (duplicate)
            (80.0, 80.0, 120.0, 130.0),  # outside ROI
        ],
        allowed={"car", "truck"},
        min_confidence=0.25,
        frame_width=640,
        frame_height=360,
        roi_norm=(0.45, 0.0, 1.0, 1.0),
        dedup_recent=[],
        dedup_iou_threshold=0.5,
        dedup_ttl_seconds=2.0,
        now_utc=now,
    )
    assert count == 1
    assert len(recent) == 1
