#!/bin/bash

URL="https://www.youtube.com/watch?v=hXtYKDio1rQ"
VIDEO=seacliff-$(date -Iminutes).mp4
TMP=/tmp/$$.mp4

yt-dlp --get-url -f best $URL > stream-url
rm -f $VIDEO $TMP
ffmpeg -i "$(cat stream-url)" -t 15 $TMP
mv $TMP $VIDEO

# https://docs.google.com/document/d/1kXs8_XJFD7oJsMW_Re105ymWb5nXnJNSQe4ze4zb2yI/edit?usp=sharing
#
# $ yt-dlp --external-downloader ffmpeg --external-downloader-args "ffmpeg:-t 00:00:10" https://www.youtube.com/watch?v=hXtYKDio1rQ
# ffmpeg -i $(cat stream-url) -f image2 -frames:v 1 img22.jpeg


