#!/bin/bash

# run at in the background and cron in the foreground

/usr/sbin/atd
/usr/sbin/cron -f
