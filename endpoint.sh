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

# pass the service account auth details to upload cached results
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/service-account-key.json

# Authenticate with Google Cloud using the service account key
if [ -f "/app/service-account-key.json" ]; then
  gcloud auth activate-service-account --key-file=/app/service-account-key.json
fi

# get the cookies so we can download the video
# March 16, 2025 - don't need the cookies because we have vpn
#gsutil cp gs://fogcat-webcam/cookies.txt /app/cookies.txt

# Check if Google DNS is already in /etc/resolv.conf
if ! grep -q "nameserver 8.8.8.8" /etc/resolv.conf; then
  echo "Adding Google DNS to /etc/resolv.conf"
  echo "nameserver 8.8.8.8" >> /etc/resolv.conf
fi

echo "=== Network Configuration ==="

# Show IP addresses and routing table
ip a | grep -E "^[0-9]+:|inet "
echo "---"
ip route

# Show NAT PREROUTING and POSTROUTING rules
echo "--- NAT Rules (PREROUTING) ---"
iptables -t nat -L PREROUTING -n -v | grep -v "Chain"

echo "--- NAT Rules (POSTROUTING) ---"
iptables -t nat -L POSTROUTING -n -v | grep -v "Chain"

# Ensure Google DNS is added if missing
if ! grep -q "nameserver 8.8.8.8" /etc/resolv.conf; then
  echo "Adding Google DNS..."
  echo "nameserver 8.8.8.8" >> /etc/resolv.conf
fi

# Show current DNS configuration
echo "--- /etc/resolv.conf ---"
grep "nameserver" /etc/resolv.conf

# Check external IP and VPN status
echo "--- External IP Info (ifconfig.me) ---"
echo "external addr $(curl -s ifconfig.me)"

echo "--- IP location (ip-api.com)"
curl ip-api.com


echo "starting API service"
/usr/local/bin/python3 app.py &

/usr/bin/tail -f /var/log/camera-collector
