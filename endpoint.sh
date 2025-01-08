#!/bin/bash
# make sure the times in crontab and at jobs are in Pacific time, not UTC
export TZ="America/Los_Angeles"

# run atd in the background and cron in the foreground
touch /var/log/cron

/usr/sbin/atd
/etc/init.d/inetutils-syslogd start
/app/sun.py
/usr/sbin/cron & \
  /usr/bin/tail -f /var/log/syslog | \
    /usr/bin/grep --line-buffered CRON
