#!/bin/bash
# make sure the times in crontab and at jobs are in Pacific time, not UTC
export TZ="America/Los_Angeles"

# run atd and cron in the background, tail the log output for the workload
touch /var/log/cron
touch /var/log/camera-collector

/usr/sbin/atd
/etc/init.d/inetutils-syslogd start
/app/sun.py
/usr/sbin/cron

# get the cookies so we can download the video
gsutil cp gs://fogcat-webcam/cookies.txt /app/cookies.txt

echo "starting API service"
/usr/local/bin/python3 app.py &

/usr/bin/tail -f /var/log/camera-collector
