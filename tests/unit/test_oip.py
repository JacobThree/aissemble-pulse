"""OIP URL building."""

from city_pulse.oip import infer_url


def test_infer_url_strips_slash() -> None:
    assert (
        infer_url("http://localhost:8080/", "yolov8")
        == "http://localhost:8080/v2/models/yolov8/infer"
    )
