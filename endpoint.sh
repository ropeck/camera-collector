#!/bin/bash
# make sure the times in crontab and at jobs are in Pacific time, not UTC
export TZ="America/Los_Angeles"

# run atd in the background and cron in the foreground
touch /var/log/cron

/usr/sbin/atd
/etc/init.d/inetutils-syslogd start
/usr/bin/python3 /app/sun.py
/usr/sbin/cron & tail -f /var/log/syslog | grep --line-buffered CRON
