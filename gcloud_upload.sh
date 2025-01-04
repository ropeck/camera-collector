#!/bin/bash

# yt-dlp is in /usr/local/bin
PATH=$PATH:/usr/sbin:/usr/bin:/bin:/usr/local/bin
PATH=$PATH:/root/google-cloud-sdk/bin:/usr/sbin

# Authenticate with Google Cloud using the service account key
if [ -f "/app/service-account-key.json" ]; then
  gcloud auth activate-service-account --key-file=/app/service-account-key.json
fi

# Set the default project (optional if your key file already contains the project ID)
gcloud config set project k8s-project-441922 --quiet
bash /app/save_video.sh

echo "$(/usr/bin/date) uploading video $(ls *.mp4)
pwd
ls -l *.mp4

# upload to GCS bucket in directory by year/month
gcloud storage cp *.mp4 gs://fogcat-webcam/$(date +%Y/%m)/


rm *.mp4
echo "$(/usr/bin/date) File uploaded to GCS successfully!"
