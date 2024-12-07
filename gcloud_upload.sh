#!/bin/bash

PATH=$PATH:/root/google-cloud-sdk/bin:/usr/sbin

# Authenticate with Google Cloud using the service account key
if [ -f "/app/service-account-key.json" ]; then
  gcloud auth activate-service-account --key-file=/app/service-account-key.json
fi

# Set the default project (optional if your key file already contains the project ID)
gcloud config set project k8s-project --quiet
bash /app/save_video.sh

# Upload the file to GCS
# Replace "your-bucket-name" and "your-object-path" with your bucket and file details
gsutil cp /app/*.mp4 gs://fogcat-webcam/

ls -l *.mp4
rm *.mp4
echo "File uploaded to GCS successfully!"
