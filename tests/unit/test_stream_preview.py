"""HLS embed helper."""

from city_pulse.dashboard.stream_preview import hls_preview_html


def test_hls_preview_contains_json_escaped_url() -> None:
    url = "https://example.invalid/live/playlist.m3u8"
    html = hls_preview_html(url)
    assert "https://example.invalid/live/playlist.m3u8" in html
    assert "hls.js" in html.lower()
