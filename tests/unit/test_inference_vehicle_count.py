"""Pure helpers for MLServer output parsing + counting."""

from city_pulse.workers.inference import (
    count_vehicle_detections,
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
