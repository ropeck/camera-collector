import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime
import tempfile
import os

from PIL import Image

from collage import (
    list_videos_from_gcs,
    extract_hour_from_filename,
    download_video_from_gcs,
    extract_frame_from_video,
    create_grid_collage,
    upload_collage_to_gcs,
    generate_collage,
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

    def test_returns_none_for_malformed_time(self):
        """Test returns None when time part is malformed."""
        assert extract_hour_from_filename("seacliff-2025-01-24.mp4") is None


class TestListVideosFromGCS:
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

        result = list_videos_from_gcs(mock_client, "test-bucket", year=2025, month=1)

        assert len(result) == 2
        mock_bucket.list_blobs.assert_called_once_with(prefix="2025/01/")

    def test_filters_non_mp4_files(self):
        """Test that non-mp4 files are filtered out."""
        mock_blob1 = MagicMock()
        mock_blob1.name = "2025/01/seacliff-2025-01-24T14:30-15-0800.mp4"
        mock_blob2 = MagicMock()
        mock_blob2.name = "2025/01/some-image.jpg"
        mock_blob3 = MagicMock()
        mock_blob3.name = "2025/01/collages/collage.jpg"

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob1, mock_blob2, mock_blob3]

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        result = list_videos_from_gcs(mock_client, "test-bucket", year=2025, month=1)

        assert len(result) == 1
        assert result[0].endswith(".mp4")

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

        result = list_videos_from_gcs(
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

        result = list_videos_from_gcs(
            mock_client, "test-bucket", year=2025, month=1, time_filter="sunrise"
        )

        assert len(result) == 1
        assert "07:00" in result[0]

    def test_respects_limit(self):
        """Test that limit parameter is respected."""
        mock_blobs = []
        for i in range(10):
            blob = MagicMock()
            blob.name = f"2025/01/seacliff-2025-01-{i+1:02d}T14:30-00-0800.mp4"
            mock_blobs.append(blob)

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = mock_blobs

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        result = list_videos_from_gcs(mock_client, "test-bucket", year=2025, month=1, limit=5)

        assert len(result) == 5

    def test_uses_current_date_by_default(self):
        """Test that current year/month is used when not specified."""
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = []

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        now = datetime.now()
        list_videos_from_gcs(mock_client, "test-bucket")

        expected_prefix = f"{now.year}/{now.month:02d}/"
        mock_bucket.list_blobs.assert_called_once_with(prefix=expected_prefix)


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


class TestExtractFrameFromVideo:
    def test_extracts_frame_with_ffmpeg(self):
        """Test frame extraction calls ffmpeg correctly."""
        mock_image = MagicMock(spec=Image.Image)
        mock_image.copy.return_value = mock_image

        with patch("subprocess.run") as mock_run, \
             patch("PIL.Image.open", return_value=mock_image), \
             patch("os.path.exists", return_value=True), \
             patch("os.remove"):

            mock_run.return_value = MagicMock(returncode=0)

            result = extract_frame_from_video("/tmp/video.mp4", timestamp_sec=5.0)

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "ffmpeg" in cmd
            assert "-ss" in cmd
            assert "5.0" in cmd
            assert "-vframes" in cmd
            assert "1" in cmd

    def test_raises_on_ffmpeg_failure(self):
        """Test that RuntimeError is raised when ffmpeg fails."""
        with patch("subprocess.run") as mock_run, \
             patch("os.path.exists", return_value=False), \
             patch("os.remove"):

            mock_run.return_value = MagicMock(
                returncode=1,
                stderr=b"ffmpeg error message"
            )

            with pytest.raises(RuntimeError, match="ffmpeg failed"):
                extract_frame_from_video("/tmp/video.mp4")

    def test_cleans_up_temp_file(self):
        """Test that temporary file is cleaned up."""
        mock_image = MagicMock(spec=Image.Image)
        mock_image.copy.return_value = mock_image

        with patch("subprocess.run") as mock_run, \
             patch("PIL.Image.open", return_value=mock_image), \
             patch("os.path.exists", return_value=True) as mock_exists, \
             patch("os.remove") as mock_remove:

            mock_run.return_value = MagicMock(returncode=0)

            extract_frame_from_video("/tmp/video.mp4")

            mock_remove.assert_called_once()


class TestCreateGridCollage:
    def test_creates_collage_with_correct_dimensions(self):
        """Test that collage has correct dimensions."""
        # Create test images
        images = [Image.new("RGB", (100, 100), color="red") for _ in range(6)]

        collage = create_grid_collage(
            images,
            grid_cols=3,
            grid_rows=2,
            thumb_width=100,
            thumb_height=100,
            padding=0,
        )

        assert collage.width == 300
        assert collage.height == 200

    def test_creates_collage_with_padding(self):
        """Test that collage includes padding."""
        images = [Image.new("RGB", (100, 100), color="red") for _ in range(4)]

        collage = create_grid_collage(
            images,
            grid_cols=2,
            grid_rows=2,
            thumb_width=100,
            thumb_height=100,
            padding=10,
        )

        # Width: 10 + 100 + 10 + 100 + 10 = 230
        # Height: 10 + 100 + 10 + 100 + 10 = 230
        assert collage.width == 230
        assert collage.height == 230

    def test_handles_fewer_images_than_grid_size(self):
        """Test that collage handles fewer images than grid capacity."""
        images = [Image.new("RGB", (100, 100), color="blue") for _ in range(3)]

        # Should not raise even with only 3 images for a 2x2 grid
        collage = create_grid_collage(images, grid_cols=2, grid_rows=2)

        assert collage is not None

    def test_handles_more_images_than_grid_size(self):
        """Test that extra images are ignored."""
        images = [Image.new("RGB", (100, 100), color="green") for _ in range(10)]

        collage = create_grid_collage(
            images,
            grid_cols=2,
            grid_rows=2,
            thumb_width=100,
            thumb_height=100,
            padding=0,
        )

        # Only 4 images should be used (2x2)
        assert collage.width == 200
        assert collage.height == 200


class TestUploadCollageToGCS:
    def test_uploads_collage_image(self):
        """Test uploading collage to GCS."""
        mock_blob = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        test_image = Image.new("RGB", (100, 100), color="red")

        with patch("os.path.exists", return_value=True), \
             patch("os.remove"):

            url = upload_collage_to_gcs(
                mock_client, "test-bucket", test_image, "2025/01/collages/test.jpg"
            )

        mock_bucket.blob.assert_called_once_with("2025/01/collages/test.jpg")
        mock_blob.upload_from_filename.assert_called_once()
        assert "test-bucket" in url
        assert "2025/01/collages/test.jpg" in url


class TestGenerateCollage:
    def test_generates_collage_end_to_end(self):
        """Test full collage generation workflow."""
        # Mock video listing
        mock_blob = MagicMock()
        mock_blob.name = "2025/01/seacliff-2025-01-24T18:30-00-0800.mp4"

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob]
        mock_upload_blob = MagicMock()
        mock_bucket.blob.return_value = mock_upload_blob

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        test_image = Image.new("RGB", (100, 100), color="red")

        with patch("collage.download_video_from_gcs"), \
             patch("collage.extract_frame_from_video", return_value=test_image), \
             patch("os.remove"), \
             patch("os.path.exists", return_value=True):

            result = generate_collage(
                mock_client,
                "test-bucket",
                year=2025,
                month=1,
                time_filter="sunset",
                grid_cols=1,
                grid_rows=1,
            )

        assert "collage_url" in result
        assert "videos_used" in result
        assert "grid_size" in result
        assert result["videos_used"] == 1
        assert result["grid_size"] == "1x1"

    def test_raises_when_no_videos_found(self):
        """Test that ValueError is raised when no videos match filter."""
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = []

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        with pytest.raises(ValueError, match="No videos found"):
            generate_collage(mock_client, "test-bucket", year=2025, month=1)

    def test_raises_when_all_frame_extractions_fail(self):
        """Test that ValueError is raised when no frames can be extracted."""
        mock_blob = MagicMock()
        mock_blob.name = "2025/01/seacliff-2025-01-24T18:30-00-0800.mp4"

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob]

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        with patch("collage.download_video_from_gcs", side_effect=Exception("Download failed")):

            with pytest.raises(ValueError, match="Failed to extract frames"):
                generate_collage(mock_client, "test-bucket", year=2025, month=1)


class TestTimeRanges:
    def test_sunrise_range(self):
        """Test sunrise hour range constants."""
        assert SUNRISE_HOUR_RANGE == (5, 10)

    def test_sunset_range(self):
        """Test sunset hour range constants."""
        assert SUNSET_HOUR_RANGE == (16, 21)
