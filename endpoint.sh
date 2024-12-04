#!/bin/bash

# run at in the background and cron in the foreground

touch /var/log/cron

/usr/sbin/atd
/etc/init.d/inetutils-syslogd start
/usr/sbin/cron & tail -f /var/log/syslog | grep --line-buffered CRON
