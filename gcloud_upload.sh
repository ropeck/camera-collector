#!/bin/bash

# yt-dlp is in /usr/local/bin
PATH=$PATH:/usr/sbin:/usr/bin:/bin:/usr/local/bin
PATH=$PATH:/root/google-cloud-sdk/bin:/usr/sbin

# Authenticate with Google Cloud using the service account key
if [ -f "/app/service-account-key.json" ]; then
  gcloud auth activate-service-account --key-file=/app/service-account-key.json
fi

# Set the default project (optional if your key file already contains the project ID)
gcloud config set project k8s-project --quiet
bash /app/save_video.sh

# upload to GCS bucket in directory by year/month
gcloud storage cp /app/*.mp4 gs://fogcat-webcam/$(date +%Y/%m)/

ls -l *.mp4
rm *.mp4
echo "$(/usr/bin/date) File uploaded to GCS successfully!"
