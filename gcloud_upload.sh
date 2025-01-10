#!/bin/bash

log () {
  msg="[$(/usr/bin/date)] $*"
  echo "$msg"
  echo "$msg" >> /var/log/camera-collector
}
# yt-dlp is in /usr/local/bin
PATH=$PATH:/usr/sbin:/usr/bin:/bin:/usr/local/bin
PATH=$PATH:/root/google-cloud-sdk/bin:/usr/sbin

# Authenticate with Google Cloud using the service account key
if [ -f "/app/service-account-key.json" ]; then
  gcloud auth activate-service-account --key-file=/app/service-account-key.json
fi

# Set the default project (optional if your key file already contains the project ID)
gcloud config set project k8s-project-441922 --quiet
cd /app || exit

log "starting video collection"
# only run one video collection at a time, coordinated by flock
flock -n /tmp/video.lock /app/save_video.sh || \
  ( echo "$(/usr/bin/date) video lock busy - exiting"; exit)

video="$(ls ./*.mp4 | sed -e 's-.*/--')"
gcspath="gs://fogcat-webcam/$(date +%Y/%m)/$video"
log "uploading video $video to $gcspath"

# upload to GCS bucket in directory by year/month
gcloud storage cp "$video" "$gcspath"

rm "$video"
log "File uploaded to GCS successfully!"
