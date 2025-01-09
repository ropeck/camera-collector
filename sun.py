#!/usr/local/bin/python3

from datetime import datetime, timedelta
from astral import LocationInfo
from astral.sun import sun
import pytz
import os

def log(message):
    print(message)
    with open("/var/log/camera-collector", "a") as f:
        t = datetime.now(pytz.timezone(os.getenv("TZ", "America/Los_Angeles")))
        timestamp = t.strftime("[%a %b %d %H:%M:%S PST %Y]")
        f.write(f"{timestamp} {message}\n")

def as_local_time(t):
    return t.astimezone(pytz.timezone(os.getenv("TZ", "America/Los_Angeles")))

def run_script(run_time):
    local_run_time = as_local_time(run_time)
    if datetime.now(pytz.timezone('US/Pacific')) > local_run_time:
        log(f"past {run_time} not scheduling today")
        return
    command = f"/usr/bin/echo '(/app/gcloud_upload.sh 2>&1 </dev/null) >> /var/log/video' | /usr/bin/at {local_run_time.strftime('%I:%M %p')}"
    log(command)
    os.system(command)

location = LocationInfo("Seacliff", "USA", "America/Los_Angeles", 36.9741, -121.9158)
local_tz = pytz.timezone(location.timezone)

today = datetime.now(local_tz)
s = sun(location.observer, date=today)

sunset_local = as_local_time(s['sunset'])
sunrise_local = as_local_time(s['sunrise'])

run_script(sunrise_local)
run_script(sunset_local - timedelta(minutes=15))
run_script(sunset_local)
os.system("/usr/bin/atq")
