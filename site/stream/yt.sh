#!/bin/bash
# mediamtx runOnReady for cam-principal: the video goes to YouTube Live as is (no re-encode, the server has 1 CPU).
# YT_KEY comes from /etc/biofut-stream.env. No key: wait (the recording still runs).
[ -n "${YT_KEY:-}" ] || exec sleep infinity
# ffmpeg errors print the RTMP URL: the key is masked before it reaches the journal. exec: mediamtx stops ffmpeg itself.
exec ffmpeg -hide_banner -loglevel warning -rtsp_transport tcp -i rtsp://127.0.0.1:8554/cam-principal \
  -c:v copy -c:a aac -b:a 128k -ar 44100 -f flv "rtmp://a.rtmp.youtube.com/live2/$YT_KEY" 2> >(sed -u "s/$YT_KEY/<key>/g" >&2)
