#!/usr/bin/env bash
# Webcam -> H.264 -> MediaMTX (rtsp://localhost:8554/litter). Started by MediaMTX.
# If the hardware encoder doesn't work on your Pi, change ENCODER to libx264.
ENCODER="h264_v4l2m2m"
DEVICE="/dev/video0"
SIZE="640x480"
FPS=10

if [ "$ENCODER" = "libx264" ]; then
  ENC_OPTS=(-c:v libx264 -preset ultrafast -tune zerolatency -b:v 800k)
else
  ENC_OPTS=(-c:v h264_v4l2m2m -b:v 800k)
fi

exec ffmpeg -hide_banner -loglevel warning \
  -f v4l2 -input_format mjpeg -video_size "$SIZE" -framerate "$FPS" -i "$DEVICE" \
  -pix_fmt yuv420p "${ENC_OPTS[@]}" -g $((FPS * 2)) \
  -f rtsp -rtsp_transport tcp rtsp://localhost:8554/litter
