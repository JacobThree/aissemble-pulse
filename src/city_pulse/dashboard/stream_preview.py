"""Embedded HLS preview for Streamlit (hls.js for Chrome/Firefox; Safari native)."""

from __future__ import annotations

import json


def hls_preview_html(m3u8_url: str, *, video_height_px: int = 360) -> str:
    """Return HTML+JS for an auto-playing-capable live HLS player (URL JSON-escaped)."""
    src = json.dumps(m3u8_url)
    h = int(video_height_px)
    err_html = (
        '<p style="color:#faa;padding:8px;font-family:sans-serif;">'
        "HLS playback not supported in this embedded context.</p>"
    )
    err_lit = json.dumps(err_html)
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/></head>
<body style="margin:0;background:#111;">
<video id="cp-hls" controls playsinline muted
 style="width:100%;height:{h}px;object-fit:contain;background:#000;"></video>
<script src="https://cdn.jsdelivr.net/npm/hls.js@1.5.7"></script>
<script>
(function () {{
  var src = {src};
  var video = document.getElementById('cp-hls');
  if (typeof Hls !== 'undefined' && Hls.isSupported()) {{
    var hls = new Hls({{ maxBufferLength: 30, liveSyncDurationCount: 3 }});
    hls.loadSource(src);
    hls.attachMedia(video);
    hls.on(Hls.Events.ERROR, function (_, data) {{
      if (data.fatal) {{ console.error('HLS fatal', data); }}
    }});
  }} else if (video.canPlayType('application/vnd.apple.mpegurl')) {{
    video.src = src;
  }} else {{
    video.outerHTML = {err_lit};
  }}
}})();
</script>
</body></html>"""
