"""Pure helpers for MLServer output parsing + counting."""

from city_pulse.workers.inference import (
    count_vehicle_detections,
    parse_bboxes,
    parse_infer_outputs,
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
