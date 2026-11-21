#!/bin/bash
# mediamtx runOnAvailable for every camera: the video goes to YouTube Live as is (no re-encode, the server has 1 CPU).
# Keys come from /etc/biofut-stream.env: YT_KEY for cam-principal, YT_KEY_GOL_NORTE for cam-gol-norte, and so on.
# One YouTube stream key per camera. No key for this camera: wait (the recording still runs).
v=YT_KEY_$(printf %s "${MTX_PATH#cam-}" | tr a-z- A-Z_)
K=${!v:-}
[ "$MTX_PATH" = cam-principal ] && K=${K:-${YT_KEY:-}}
[ -n "$K" ] || exec sleep infinity
# ffmpeg errors print the RTMP URL: the key is masked before it reaches the journal. exec: mediamtx stops ffmpeg itself.
exec ffmpeg -hide_banner -loglevel warning -rtsp_transport tcp -i "rtsp://127.0.0.1:8554/$MTX_PATH" \
  -c:v copy -c:a aac -b:a 128k -ar 44100 -f flv "rtmp://a.rtmp.youtube.com/live2/$K" 2> >(sed -u "s/$K/<key>/g" >&2)
