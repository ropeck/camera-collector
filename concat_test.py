import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
import tempfile
import os

from concat import (
    list_videos_for_month,
    get_video_counts_for_month,
    get_compilation_blob_name,
    check_compilation_exists,
    download_video_from_gcs,
    concatenate_videos,
    upload_compilation_to_gcs,
    get_video_duration,
    generate_compilation,
    list_available_months,
    extract_hour_from_filename,
    SUNRISE_HOUR_RANGE,
    SUNSET_HOUR_RANGE,
)


class TestExtractHourFromFilename:
    def test_extracts_hour_correctly(self):
        """Test extracting hour from standard filename."""
        filename = "seacliff-2025-01-24T14:30-15-0800.mp4"
        assert extract_hour_from_filename(filename) == 14

    def test_extracts_morning_hour(self):
        """Test extracting morning hour."""
        filename = "2025/01/seacliff-2025-01-24T06:45-00-0800.mp4"
        assert extract_hour_from_filename(filename) == 6

    def test_extracts_evening_hour(self):
        """Test extracting evening hour."""
        filename = "seacliff-2025-01-24T19:15-30-0800.mp4"
        assert extract_hour_from_filename(filename) == 19

    def test_returns_none_for_invalid_filename(self):
        """Test returns None for invalid filename format."""
        assert extract_hour_from_filename("invalid.mp4") is None
        assert extract_hour_from_filename("no-timestamp.mp4") is None


class TestListVideosForMonth:
    def test_lists_videos_with_prefix(self):
        """Test listing videos with year/month prefix."""
        mock_blob1 = MagicMock()
        mock_blob1.name = "2025/01/seacliff-2025-01-24T14:30-15-0800.mp4"
        mock_blob2 = MagicMock()
        mock_blob2.name = "2025/01/seacliff-2025-01-25T07:00-00-0800.mp4"

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob1, mock_blob2]

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        result = list_videos_for_month(mock_client, "test-bucket", year=2025, month=1)

        assert len(result) == 2
        mock_bucket.list_blobs.assert_called_once_with(prefix="2025/01/")

    def test_filters_non_mp4_files(self):
        """Test that non-mp4 files are filtered out."""
        mock_blob1 = MagicMock()
        mock_blob1.name = "2025/01/seacliff-2025-01-24T14:30-15-0800.mp4"
        mock_blob2 = MagicMock()
        mock_blob2.name = "2025/01/some-image.jpg"

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob1, mock_blob2]

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        result = list_videos_for_month(mock_client, "test-bucket", year=2025, month=1)

        assert len(result) == 1
        assert result[0].endswith(".mp4")

    def test_excludes_compilations_directory(self):
        """Test that videos in compilations/ directory are excluded."""
        mock_blob1 = MagicMock()
        mock_blob1.name = "2025/01/seacliff-2025-01-24T14:30-15-0800.mp4"
        mock_blob2 = MagicMock()
        mock_blob2.name = "2025/01/compilations/sunset-2025-01.mp4"

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob1, mock_blob2]

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        result = list_videos_for_month(mock_client, "test-bucket", year=2025, month=1)

        assert len(result) == 1
        assert "compilations" not in result[0]

    def test_excludes_collages_directory(self):
        """Test that videos in collages/ directory are excluded."""
        mock_blob1 = MagicMock()
        mock_blob1.name = "2025/01/seacliff-2025-01-24T14:30-15-0800.mp4"
        mock_blob2 = MagicMock()
        mock_blob2.name = "2025/01/collages/collage.jpg"

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob1, mock_blob2]

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        result = list_videos_for_month(mock_client, "test-bucket", year=2025, month=1)

        assert len(result) == 1
        assert "collages" not in result[0]

    def test_filters_by_sunset_time(self):
        """Test filtering videos by sunset time range."""
        mock_blob_morning = MagicMock()
        mock_blob_morning.name = "2025/01/seacliff-2025-01-24T07:00-00-0800.mp4"
        mock_blob_evening = MagicMock()
        mock_blob_evening.name = "2025/01/seacliff-2025-01-24T18:30-00-0800.mp4"

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob_morning, mock_blob_evening]

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        result = list_videos_for_month(
            mock_client, "test-bucket", year=2025, month=1, time_filter="sunset"
        )

        assert len(result) == 1
        assert "18:30" in result[0]

    def test_filters_by_sunrise_time(self):
        """Test filtering videos by sunrise time range."""
        mock_blob_morning = MagicMock()
        mock_blob_morning.name = "2025/01/seacliff-2025-01-24T07:00-00-0800.mp4"
        mock_blob_evening = MagicMock()
        mock_blob_evening.name = "2025/01/seacliff-2025-01-24T18:30-00-0800.mp4"

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob_morning, mock_blob_evening]

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        result = list_videos_for_month(
            mock_client, "test-bucket", year=2025, month=1, time_filter="sunrise"
        )

        assert len(result) == 1
        assert "07:00" in result[0]

    def test_returns_sorted_list(self):
        """Test that results are sorted chronologically."""
        mock_blob1 = MagicMock()
        mock_blob1.name = "2025/01/seacliff-2025-01-25T14:30-00-0800.mp4"
        mock_blob2 = MagicMock()
        mock_blob2.name = "2025/01/seacliff-2025-01-24T07:00-00-0800.mp4"

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob1, mock_blob2]

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        result = list_videos_for_month(mock_client, "test-bucket", year=2025, month=1)

        assert "01-24" in result[0]
        assert "01-25" in result[1]


class TestGetVideoCountsForMonth:
    def test_returns_counts_for_all_categories(self):
        """Test that counts are returned for sunrise, sunset, and total."""
        mock_blob_morning = MagicMock()
        mock_blob_morning.name = "2025/01/seacliff-2025-01-24T07:00-00-0800.mp4"
        mock_blob_evening = MagicMock()
        mock_blob_evening.name = "2025/01/seacliff-2025-01-24T18:30-00-0800.mp4"

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob_morning, mock_blob_evening]

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        result = get_video_counts_for_month(mock_client, "test-bucket", year=2025, month=1)

        assert "sunrise_count" in result
        assert "sunset_count" in result
        assert "total_count" in result


class TestGetCompilationBlobName:
    def test_generates_sunrise_blob_name(self):
        """Test generating blob name for sunrise compilation."""
        result = get_compilation_blob_name(2025, 1, "sunrise")
        assert result == "2025/01/compilations/sunrise-2025-01.mp4"

    def test_generates_sunset_blob_name(self):
        """Test generating blob name for sunset compilation."""
        result = get_compilation_blob_name(2025, 1, "sunset")
        assert result == "2025/01/compilations/sunset-2025-01.mp4"

    def test_generates_all_blob_name(self):
        """Test generating blob name for all-videos compilation."""
        result = get_compilation_blob_name(2025, 1, None)
        assert result == "2025/01/compilations/all-2025-01.mp4"

    def test_pads_month_with_zero(self):
        """Test that single-digit months are zero-padded."""
        result = get_compilation_blob_name(2025, 3, "sunrise")
        assert "03" in result


class TestCheckCompilationExists:
    def test_returns_true_when_exists(self):
        """Test returns exists=True when compilation exists."""
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_blob.size = 100000000
        mock_blob.updated = datetime(2025, 1, 24, 10, 30, 0)

        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        result = check_compilation_exists(
            mock_client, "test-bucket", "2025/01/compilations/sunset-2025-01.mp4"
        )

        assert result["exists"] is True
        assert "url" in result
        assert result["size_bytes"] == 100000000

    def test_returns_false_when_not_exists(self):
        """Test returns exists=False when compilation doesn't exist."""
        mock_blob = MagicMock()
        mock_blob.exists.return_value = False

        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        result = check_compilation_exists(
            mock_client, "test-bucket", "2025/01/compilations/sunset-2025-01.mp4"
        )

        assert result["exists"] is False


class TestDownloadVideoFromGCS:
    def test_downloads_to_local_path(self):
        """Test downloading video to local path."""
        mock_blob = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        download_video_from_gcs(
            mock_client, "test-bucket", "2025/01/video.mp4", "/tmp/video.mp4"
        )

        mock_bucket.blob.assert_called_once_with("2025/01/video.mp4")
        mock_blob.download_to_filename.assert_called_once_with("/tmp/video.mp4")


class TestConcatenateVideos:
    def test_raises_on_empty_list(self):
        """Test that ValueError is raised when video list is empty."""
        with pytest.raises(ValueError, match="No video paths provided"):
            concatenate_videos([], "/tmp/output.mp4")

    def test_calls_ffmpeg_with_concat_demuxer(self):
        """Test that ffmpeg is called with concat demuxer."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create fake video files
            video1 = os.path.join(tmp_dir, "video1.mp4")
            video2 = os.path.join(tmp_dir, "video2.mp4")
            output = os.path.join(tmp_dir, "output.mp4")

            with open(video1, "w") as f:
                f.write("fake")
            with open(video2, "w") as f:
                f.write("fake")

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                concatenate_videos([video1, video2], output)

                mock_run.assert_called_once()
                cmd = mock_run.call_args[0][0]
                assert "ffmpeg" in cmd
                assert "-f" in cmd
                assert "concat" in cmd
                assert "-c" in cmd
                assert "copy" in cmd
                assert "-movflags" in cmd
                assert "+faststart" in cmd

    def test_raises_on_ffmpeg_failure(self):
        """Test that RuntimeError is raised when ffmpeg fails."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            video1 = os.path.join(tmp_dir, "video1.mp4")
            output = os.path.join(tmp_dir, "output.mp4")

            with open(video1, "w") as f:
                f.write("fake")

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1,
                    stderr=b"ffmpeg error message"
                )

                with pytest.raises(RuntimeError, match="ffmpeg concat failed"):
                    concatenate_videos([video1], output)


class TestUploadCompilationToGCS:
    def test_uploads_video_file(self):
        """Test uploading compilation to GCS."""
        mock_blob = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"fake video content")
            tmp_path = f.name

        try:
            url = upload_compilation_to_gcs(
                mock_client, "test-bucket", tmp_path, "2025/01/compilations/test.mp4"
            )

            mock_bucket.blob.assert_called_once_with("2025/01/compilations/test.mp4")
            mock_blob.upload_from_filename.assert_called_once()
            assert "test-bucket" in url
            assert "test.mp4" in url
        finally:
            os.unlink(tmp_path)


class TestGetVideoDuration:
    def test_returns_duration_from_ffprobe(self):
        """Test getting video duration."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=b"15.5"
            )

            duration = get_video_duration("/tmp/video.mp4")

            assert duration == 15.5
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "ffprobe" in cmd

    def test_returns_zero_on_failure(self):
        """Test returns 0 when ffprobe fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=b"")

            duration = get_video_duration("/tmp/video.mp4")

            assert duration == 0.0


class TestGenerateCompilation:
    def test_returns_cached_when_exists(self):
        """Test returns cached compilation when it exists."""
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_blob.size = 100000000
        mock_blob.updated = datetime(2025, 1, 24, 10, 30, 0)

        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        result = generate_compilation(
            mock_client, "test-bucket", year=2025, month=1, time_filter="sunset"
        )

        assert result["cached"] is True
        assert "url" in result

    def test_generates_when_not_cached(self):
        """Test generates compilation when not cached."""
        # First call to check_compilation_exists returns not exists
        mock_blob_not_exists = MagicMock()
        mock_blob_not_exists.exists.return_value = False

        # Video blob
        mock_video_blob = MagicMock()
        mock_video_blob.name = "2025/01/seacliff-2025-01-24T18:30-00-0800.mp4"

        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob_not_exists
        mock_bucket.list_blobs.return_value = [mock_video_blob]

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        with patch("concat.download_video_from_gcs"), \
             patch("concat.concatenate_videos"), \
             patch("concat.upload_compilation_to_gcs", return_value="https://test.url"), \
             patch("concat.get_video_duration", return_value=15.0), \
             patch("os.path.getsize", return_value=1000000):

            result = generate_compilation(
                mock_client, "test-bucket", year=2025, month=1, time_filter="sunset"
            )

        assert result["cached"] is False
        assert result["video_count"] == 1
        assert result["duration_seconds"] == 15.0

    def test_raises_when_no_videos(self):
        """Test raises ValueError when no videos found."""
        mock_blob = MagicMock()
        mock_blob.exists.return_value = False

        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_bucket.list_blobs.return_value = []

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        with pytest.raises(ValueError, match="No videos found"):
            generate_compilation(
                mock_client, "test-bucket", year=2025, month=1, time_filter="sunset"
            )

    def test_force_regenerate_ignores_cache(self):
        """Test force_regenerate=True ignores cached compilation."""
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True

        mock_video_blob = MagicMock()
        mock_video_blob.name = "2025/01/seacliff-2025-01-24T18:30-00-0800.mp4"

        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_bucket.list_blobs.return_value = [mock_video_blob]

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        with patch("concat.download_video_from_gcs"), \
             patch("concat.concatenate_videos"), \
             patch("concat.upload_compilation_to_gcs", return_value="https://test.url"), \
             patch("concat.get_video_duration", return_value=15.0), \
             patch("os.path.getsize", return_value=1000000):

            result = generate_compilation(
                mock_client, "test-bucket", year=2025, month=1,
                time_filter="sunset", force_regenerate=True
            )

        # Should regenerate even though cached exists
        assert result["cached"] is False


class TestListAvailableMonths:
    def test_lists_months_with_videos(self):
        """Test listing months that have videos."""
        mock_blob1 = MagicMock()
        mock_blob1.name = "2025/01/seacliff-2025-01-24T07:00-00-0800.mp4"
        mock_blob2 = MagicMock()
        mock_blob2.name = "2025/01/seacliff-2025-01-24T18:30-00-0800.mp4"
        mock_blob3 = MagicMock()
        mock_blob3.name = "2024/12/seacliff-2024-12-15T17:00-00-0800.mp4"

        # Mock for compilation checks
        mock_compilation_blob = MagicMock()
        mock_compilation_blob.exists.return_value = False

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob1, mock_blob2, mock_blob3]
        mock_bucket.blob.return_value = mock_compilation_blob

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        result = list_available_months(mock_client, "test-bucket")

        assert len(result) >= 1
        # Results should be sorted descending by year/month
        assert result[0]["year"] >= result[-1]["year"]

    def test_excludes_compilations_from_listing(self):
        """Test that compilation files don't create phantom months."""
        mock_blob1 = MagicMock()
        mock_blob1.name = "2025/01/seacliff-2025-01-24T07:00-00-0800.mp4"
        mock_blob2 = MagicMock()
        mock_blob2.name = "2025/01/compilations/sunset-2025-01.mp4"

        mock_compilation_blob = MagicMock()
        mock_compilation_blob.exists.return_value = False

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob1, mock_blob2]
        mock_bucket.blob.return_value = mock_compilation_blob

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        result = list_available_months(mock_client, "test-bucket")

        # Should only have one month
        assert len(result) == 1


class TestTimeRanges:
    def test_sunrise_range(self):
        """Test sunrise hour range constants."""
        assert SUNRISE_HOUR_RANGE == (5, 10)

    def test_sunset_range(self):
        """Test sunset hour range constants."""
        assert SUNSET_HOUR_RANGE == (16, 21)
