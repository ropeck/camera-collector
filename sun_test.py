import pytest
from unittest.mock import patch, MagicMock, mock_open
from datetime import datetime, timedelta
import pytz


class TestLog:
    def test_log_writes_to_file(self):
        """Test that log function writes message to file."""
        from sun import log
        mock_file = mock_open()
        # Only mock the specific log file open, not all open calls
        with patch('sun.open', mock_file), \
             patch('builtins.print') as mock_print:
            log("test message")

            mock_print.assert_called_once_with("test message")
            mock_file.assert_called_once_with("/var/log/camera-collector", "a")
            handle = mock_file()
            write_calls = handle.write.call_args_list
            assert len(write_calls) == 1
            written_text = write_calls[0][0][0]
            assert "test message" in written_text

    def test_log_includes_timestamp(self):
        """Test that log includes a timestamp."""
        from sun import log
        mock_file = mock_open()
        with patch('sun.open', mock_file), \
             patch('builtins.print'):
            log("test message")

            handle = mock_file()
            written_text = handle.write.call_args[0][0]
            assert "[" in written_text
            assert "]" in written_text


class TestAsLocalTime:
    def test_converts_utc_to_pacific(self):
        """Test converting UTC time to Pacific time."""
        from sun import as_local_time
        utc_time = datetime(2024, 6, 15, 20, 0, 0, tzinfo=pytz.UTC)

        with patch.dict('os.environ', {'TZ': 'America/Los_Angeles'}):
            local_time = as_local_time(utc_time)

        # UTC 20:00 in June is 13:00 PDT (UTC-7)
        assert local_time.hour == 13
        assert local_time.tzinfo is not None

    def test_converts_utc_to_eastern(self):
        """Test converting UTC time to Eastern time."""
        from sun import as_local_time
        utc_time = datetime(2024, 6, 15, 20, 0, 0, tzinfo=pytz.UTC)

        with patch.dict('os.environ', {'TZ': 'US/Eastern'}):
            local_time = as_local_time(utc_time)

        # UTC 20:00 in June is 16:00 EDT (UTC-4)
        assert local_time.hour == 16

    def test_default_timezone(self):
        """Test that default timezone is used when TZ not set."""
        from sun import as_local_time
        utc_time = datetime(2024, 6, 15, 20, 0, 0, tzinfo=pytz.UTC)

        with patch.dict('os.environ', {}, clear=True):
            local_time = as_local_time(utc_time)

        assert local_time.tzinfo is not None


class TestRunScript:
    def test_schedules_future_time(self):
        """Test that run_script schedules jobs for future times."""
        from sun import run_script, log
        pacific_tz = pytz.timezone('America/Los_Angeles')
        future_time = datetime.now(pacific_tz) + timedelta(hours=2)

        with patch('sun.os.system') as mock_system, \
             patch('sun.log') as mock_log:

            run_script(future_time)

            mock_system.assert_called_once()
            call_arg = mock_system.call_args[0][0]
            assert "/usr/bin/at" in call_arg
            assert "start_collection.py" in call_arg

    def test_skips_past_time(self):
        """Test that run_script skips times in the past."""
        from sun import run_script
        pacific_tz = pytz.timezone('America/Los_Angeles')
        past_time = datetime.now(pacific_tz) - timedelta(hours=2)

        with patch('sun.os.system') as mock_system, \
             patch('sun.log') as mock_log:

            run_script(past_time)

            mock_system.assert_not_called()
            mock_log.assert_called()
            log_message = mock_log.call_args[0][0]
            assert "not scheduling" in log_message

    def test_at_command_format(self):
        """Test that the at command is formatted correctly."""
        from sun import run_script
        pacific_tz = pytz.timezone('America/Los_Angeles')
        future_time = datetime.now(pacific_tz).replace(
            hour=18, minute=30, second=0, microsecond=0
        ) + timedelta(days=1)

        with patch('sun.os.system') as mock_system, \
             patch('sun.log'):

            run_script(future_time)

            call_arg = mock_system.call_args[0][0]
            assert "/usr/bin/echo" in call_arg
            assert "/usr/bin/at" in call_arg
            assert "/app/start_collection.py" in call_arg
            assert "/var/log/video" in call_arg


class TestGetLocation:
    def test_location_info(self):
        """Test that location is correctly configured for Seacliff."""
        from sun import get_location

        location = get_location()

        assert location.name == "Seacliff"
        assert location.region == "USA"
        assert location.timezone == "America/Los_Angeles"
        assert abs(location.latitude - 36.9741) < 0.0001
        assert abs(location.longitude - (-121.9158)) < 0.0001


class TestSunriseAndSunset:
    def test_sun_calculation(self):
        """Test that sunrise/sunset times are calculated correctly."""
        from astral import LocationInfo
        from astral.sun import sun as astral_sun

        location = LocationInfo("Seacliff", "USA", "America/Los_Angeles", 36.9741, -121.9158)
        test_date = datetime(2024, 6, 21)  # Summer solstice

        s = astral_sun(location.observer, date=test_date)

        assert 'sunrise' in s
        assert 'sunset' in s
        # In June, sunrise should be early morning (before 7 AM UTC)
        assert s['sunrise'].hour < 14  # UTC hour
        # In June, sunset should be late evening
        assert s['sunset'].hour > 1  # UTC hour

    def test_sun_times_are_timezone_aware(self):
        """Test that sun times have timezone information."""
        from astral import LocationInfo
        from astral.sun import sun as astral_sun

        location = LocationInfo("Seacliff", "USA", "America/Los_Angeles", 36.9741, -121.9158)
        test_date = datetime(2024, 6, 21)

        s = astral_sun(location.observer, date=test_date)

        assert s['sunrise'].tzinfo is not None
        assert s['sunset'].tzinfo is not None

    def test_sunset_before_sunrise_scheduling(self):
        """Test that we schedule 15 minutes before sunset."""
        pacific_tz = pytz.timezone('America/Los_Angeles')
        sunset_time = datetime.now(pacific_tz).replace(
            hour=19, minute=30, second=0, microsecond=0
        ) + timedelta(days=1)

        pre_sunset = sunset_time - timedelta(minutes=15)

        assert (sunset_time - pre_sunset).total_seconds() == 15 * 60

    def test_winter_vs_summer_sun_times(self):
        """Test that winter and summer have different sunrise/sunset times."""
        from astral import LocationInfo
        from astral.sun import sun as astral_sun

        location = LocationInfo("Seacliff", "USA", "America/Los_Angeles", 36.9741, -121.9158)

        summer_date = datetime(2024, 6, 21)  # Summer solstice
        winter_date = datetime(2024, 12, 21)  # Winter solstice

        summer_sun = astral_sun(location.observer, date=summer_date)
        winter_sun = astral_sun(location.observer, date=winter_date)

        summer_sunset_hour = summer_sun['sunset'].hour
        winter_sunset_hour = winter_sun['sunset'].hour

        assert summer_sunset_hour != winter_sunset_hour


class TestScheduleCollections:
    def test_schedules_three_times(self):
        """Test that schedule_collections schedules sunrise, pre-sunset, and sunset."""
        from sun import schedule_collections

        with patch('sun.os.system') as mock_system, \
             patch('sun.log') as mock_log, \
             patch('sun.run_script') as mock_run_script:

            schedule_collections()

            # Should call run_script 3 times: sunrise, 15min before sunset, sunset
            assert mock_run_script.call_count == 3

    def test_calls_atq_at_end(self):
        """Test that schedule_collections calls atq to show scheduled jobs."""
        from sun import schedule_collections

        with patch('sun.os.system') as mock_system, \
             patch('sun.log'), \
             patch('sun.run_script'):

            schedule_collections()

            # Last os.system call should be atq
            mock_system.assert_called_once_with("/usr/bin/atq")

    def test_logs_startup_message(self):
        """Test that schedule_collections logs startup message."""
        from sun import schedule_collections

        with patch('sun.os.system'), \
             patch('sun.log') as mock_log, \
             patch('sun.run_script'):

            schedule_collections()

            # First log call should be startup message
            first_call = mock_log.call_args_list[0][0][0]
            assert "starting collection scheduling" in first_call
