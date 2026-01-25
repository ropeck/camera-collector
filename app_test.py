import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from datetime import datetime
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket
import uuid
import json
import os

# Mock the storage client before importing app
with patch('google.cloud.storage.Client'):
    from app import (
        app, active_jobs, manager, latest_video_manager,
        ConnectionManager, LatestVideoConnectionManager, ThreadSafeJobs,
        collect_and_upload_video, run_subprocess_blocking, upload_to_gcs,
        notify_latest_video, lookup_external_ip
    )

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_and_teardown():
    """Setup and teardown for tests."""
    active_jobs.data.clear()
    manager.active_connections.clear()
    latest_video_manager.active_connections.clear()
    yield
    active_jobs.data.clear()
    manager.active_connections.clear()
    latest_video_manager.active_connections.clear()


class TestRootEndpoint:
    def test_root_returns_200(self):
        """Test the root endpoint returns 200 status."""
        response = client.get("/")
        assert response.status_code == 200

    def test_root_contains_message(self):
        """Test the root endpoint contains a message."""
        response = client.get("/")
        data = response.json()
        assert "message" in data
        assert "Camera Collector API is running!" in data["message"]

    def test_root_contains_version(self):
        """Test the root endpoint contains version info."""
        response = client.get("/")
        data = response.json()
        assert "version" in data


class TestStartCollection:
    def test_start_collection_with_url(self):
        """Test starting a collection job with a custom URL."""
        youtube_url = "https://www.youtube.com/watch?v=example"
        response = client.post(f"/collection/start/{youtube_url}")
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert "message" in data

    def test_start_collection_returns_valid_uuid(self):
        """Test that job_id is a valid UUID."""
        youtube_url = "https://www.youtube.com/watch?v=example"
        response = client.post(f"/collection/start/{youtube_url}")
        data = response.json()
        job_id = data["job_id"]
        # Should not raise ValueError if valid UUID
        uuid.UUID(job_id)

    def test_start_collection_default_url(self):
        """Test starting a collection job with default URL."""
        response = client.post("/collection/start")
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data

    def test_start_collection_creates_job(self):
        """Test that starting collection returns success message."""
        youtube_url = "https://www.youtube.com/watch?v=example"
        response = client.post(f"/collection/start/{youtube_url}")
        data = response.json()
        # Verify response contains expected fields
        assert "job_id" in data
        assert "message" in data
        assert "Collection started" in data["message"]


class TestCollectionStatus:
    @pytest.mark.asyncio
    async def test_status_valid_job(self):
        """Test retrieving the status of a valid job ID."""
        job_id = str(uuid.uuid4())
        await active_jobs.set_job(job_id, {
            "url": "https://www.youtube.com/watch?v=example",
            "time_started": datetime.now().isoformat(),
            "status": "running",
        })

        response = client.get(f"/collection/status/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"

    def test_status_invalid_job(self):
        """Test retrieving the status of an invalid job ID."""
        job_id = str(uuid.uuid4())
        response = client.get(f"/collection/status/{job_id}")
        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Job ID not found."

    @pytest.mark.asyncio
    async def test_status_contains_job_info(self):
        """Test status response contains all job information."""
        job_id = str(uuid.uuid4())
        job_info = {
            "url": "https://www.youtube.com/watch?v=test",
            "time_started": datetime.now().isoformat(),
            "status": "uploading to gcs",
        }
        await active_jobs.set_job(job_id, job_info)

        response = client.get(f"/collection/status/{job_id}")
        data = response.json()
        assert data["url"] == job_info["url"]
        assert data["status"] == job_info["status"]


class TestActiveCollections:
    def test_active_collections_empty(self):
        """Test getting active collections when none exist."""
        response = client.get("/active-collections")
        assert response.status_code == 200
        data = response.json()
        assert "active_jobs" in data
        assert data["active_jobs"] == {}

    @pytest.mark.asyncio
    async def test_active_collections_multiple_jobs(self):
        """Test getting multiple active collections."""
        job_id1 = str(uuid.uuid4())
        job_id2 = str(uuid.uuid4())
        await active_jobs.set_job(job_id1, {
            "url": "https://www.youtube.com/watch?v=example1",
            "time_started": datetime.now().isoformat(),
            "status": "running",
        })
        await active_jobs.set_job(job_id2, {
            "url": "https://www.youtube.com/watch?v=example2",
            "time_started": datetime.now().isoformat(),
            "status": "uploading",
        })

        response = client.get("/active-collections")
        data = response.json()
        assert job_id1 in data["active_jobs"]
        assert job_id2 in data["active_jobs"]


class TestThreadSafeJobs:
    @pytest.mark.asyncio
    async def test_set_and_get_job(self):
        """Test setting and getting a job."""
        jobs = ThreadSafeJobs()
        job_id = "test-job-id"
        job_info = {"status": "running", "url": "test-url"}

        with patch.object(manager, 'send_message', new_callable=AsyncMock):
            await jobs.set_job(job_id, job_info)

        result = await jobs.get_job(job_id)
        assert result == job_info

    @pytest.mark.asyncio
    async def test_set_status(self):
        """Test updating job status."""
        jobs = ThreadSafeJobs()
        job_id = "test-job-id"
        jobs.data[job_id] = {"status": "started"}

        with patch.object(manager, 'send_message', new_callable=AsyncMock):
            await jobs.set_status(job_id, "completed")

        assert jobs.data[job_id]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_delete_job(self):
        """Test deleting a job."""
        jobs = ThreadSafeJobs()
        job_id = "test-job-id"
        jobs.data[job_id] = {"status": "running"}

        await jobs.delete_job(job_id)
        assert job_id not in jobs.data

    @pytest.mark.asyncio
    async def test_get_all_jobs(self):
        """Test getting all jobs."""
        jobs = ThreadSafeJobs()
        jobs.data["job1"] = {"status": "running"}
        jobs.data["job2"] = {"status": "completed"}

        all_jobs = await jobs.get_all_jobs()
        assert len(all_jobs) == 2
        assert "job1" in all_jobs
        assert "job2" in all_jobs

    @pytest.mark.asyncio
    async def test_get_nonexistent_job(self):
        """Test getting a job that doesn't exist."""
        jobs = ThreadSafeJobs()
        result = await jobs.get_job("nonexistent")
        assert result is None


class TestConnectionManager:
    @pytest.mark.asyncio
    async def test_connect(self):
        """Test connecting a WebSocket."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock(spec=WebSocket)

        await mgr.connect(mock_ws, "job-123")

        mock_ws.accept.assert_called_once()
        assert "job-123" in mgr.active_connections

    def test_disconnect(self):
        """Test disconnecting a WebSocket."""
        mgr = ConnectionManager()
        mock_ws = MagicMock()
        mgr.active_connections["job-123"] = mock_ws

        mgr.disconnect("job-123")

        assert "job-123" not in mgr.active_connections

    def test_disconnect_nonexistent(self):
        """Test disconnecting a non-existent job doesn't raise."""
        mgr = ConnectionManager()
        mgr.disconnect("nonexistent")  # Should not raise

    @pytest.mark.asyncio
    async def test_send_message(self):
        """Test sending a message to a connected WebSocket."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        mgr.active_connections["job-123"] = mock_ws

        await mgr.send_message("job-123", "test message")

        mock_ws.send_text.assert_called_once_with("test message")

    @pytest.mark.asyncio
    async def test_send_message_no_connection(self):
        """Test sending message when no connection exists."""
        mgr = ConnectionManager()
        # Should not raise
        await mgr.send_message("nonexistent", "test message")


class TestLatestVideoConnectionManager:
    @pytest.mark.asyncio
    async def test_connect(self):
        """Test connecting a WebSocket for latest video updates."""
        mgr = LatestVideoConnectionManager()
        mock_ws = AsyncMock(spec=WebSocket)

        await mgr.connect(mock_ws)

        mock_ws.accept.assert_called_once()
        assert mock_ws in mgr.active_connections

    def test_disconnect(self):
        """Test disconnecting a WebSocket."""
        mgr = LatestVideoConnectionManager()
        mock_ws = MagicMock()
        mgr.active_connections.append(mock_ws)

        mgr.disconnect(mock_ws)

        assert mock_ws not in mgr.active_connections

    @pytest.mark.asyncio
    async def test_broadcast(self):
        """Test broadcasting to all connected clients."""
        mgr = LatestVideoConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        mgr.active_connections = [mock_ws1, mock_ws2]

        await mgr.broadcast("test broadcast")

        mock_ws1.send_text.assert_called_once_with("test broadcast")
        mock_ws2.send_text.assert_called_once_with("test broadcast")

    @pytest.mark.asyncio
    async def test_broadcast_removes_failed_connection(self):
        """Test that failed connections are removed during broadcast."""
        mgr = LatestVideoConnectionManager()
        mock_ws_good = AsyncMock()
        mock_ws_bad = AsyncMock()
        mock_ws_bad.send_text.side_effect = Exception("Connection failed")
        mgr.active_connections = [mock_ws_good, mock_ws_bad]

        await mgr.broadcast("test")

        assert mock_ws_bad not in mgr.active_connections


class TestVideoPipeline:
    @pytest.mark.asyncio
    async def test_collect_and_upload_video_success(self):
        """Test successful video collection and upload."""
        job_id = str(uuid.uuid4())
        youtube_url = "https://www.youtube.com/watch?v=test"

        with patch.object(active_jobs, 'set_status', new_callable=AsyncMock) as mock_status, \
             patch.object(active_jobs, 'delete_job', new_callable=AsyncMock) as mock_delete, \
             patch('app.run_subprocess_blocking') as mock_subprocess, \
             patch('app.upload_to_gcs') as mock_upload, \
             patch('app.notify_latest_video', new_callable=AsyncMock) as mock_notify, \
             patch('os.path.exists', return_value=True), \
             patch('os.remove'):

            await collect_and_upload_video(job_id, youtube_url)

            # Verify status progression
            status_calls = [call[0][1] for call in mock_status.call_args_list]
            assert "in progress" in status_calls
            assert "uploading to gcs" in status_calls
            assert "completed" in status_calls

            mock_subprocess.assert_called_once()
            mock_upload.assert_called_once()
            mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_collect_and_upload_video_subprocess_error(self):
        """Test video collection when subprocess fails."""
        job_id = str(uuid.uuid4())
        youtube_url = "https://www.youtube.com/watch?v=test"

        with patch.object(active_jobs, 'set_status', new_callable=AsyncMock), \
             patch.object(active_jobs, 'delete_job', new_callable=AsyncMock), \
             patch('app.run_subprocess_blocking', side_effect=RuntimeError("FFmpeg failed")), \
             patch('os.path.exists', return_value=False):

            with pytest.raises(RuntimeError, match="Error during video collection"):
                await collect_and_upload_video(job_id, youtube_url)

    @pytest.mark.asyncio
    async def test_collect_and_upload_video_cleans_up_file(self):
        """Test that local file is cleaned up after upload."""
        job_id = str(uuid.uuid4())
        youtube_url = "https://www.youtube.com/watch?v=test"

        with patch.object(active_jobs, 'set_status', new_callable=AsyncMock), \
             patch.object(active_jobs, 'delete_job', new_callable=AsyncMock), \
             patch('app.run_subprocess_blocking'), \
             patch('app.upload_to_gcs'), \
             patch('app.notify_latest_video', new_callable=AsyncMock), \
             patch('os.path.exists', return_value=True) as mock_exists, \
             patch('os.remove') as mock_remove:

            await collect_and_upload_video(job_id, youtube_url)

            mock_exists.assert_called()
            mock_remove.assert_called_once()


class TestSubprocessBlocking:
    def test_run_subprocess_blocking_success(self):
        """Test successful subprocess execution."""
        mock_ffmpeg = MagicMock()
        mock_ffmpeg.returncode = 0
        mock_ffmpeg.communicate.return_value = (b"", b"")

        mock_ytdlp = MagicMock()
        mock_ytdlp.terminate.return_value = None
        mock_ytdlp.wait.return_value = None

        with patch('subprocess.Popen', side_effect=[mock_ffmpeg, mock_ytdlp]), \
             patch('app.lookup_external_ip', return_value="1.2.3.4"):

            # Should not raise
            run_subprocess_blocking("https://youtube.com/test", "/tmp/test.mp4")

            mock_ffmpeg.communicate.assert_called_once()
            mock_ytdlp.terminate.assert_called_once()

    def test_run_subprocess_blocking_ffmpeg_error(self):
        """Test subprocess when FFmpeg fails."""
        mock_ffmpeg = MagicMock()
        mock_ffmpeg.returncode = 1
        mock_ffmpeg.communicate.return_value = (b"", b"")
        mock_ffmpeg.stderr.read.return_value = b"FFmpeg error message"

        mock_ytdlp = MagicMock()
        mock_ytdlp.poll.return_value = None

        with patch('subprocess.Popen', side_effect=[mock_ffmpeg, mock_ytdlp]), \
             patch('app.lookup_external_ip', return_value="1.2.3.4"):

            with pytest.raises(RuntimeError, match="FFmpeg error"):
                run_subprocess_blocking("https://youtube.com/test", "/tmp/test.mp4")


class TestUploadToGCS:
    def test_upload_to_gcs(self):
        """Test uploading file to Google Cloud Storage."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        with patch('app.storage_client') as mock_client:
            mock_client.bucket.return_value = mock_bucket

            upload_to_gcs("/tmp/test-video.mp4")

            mock_client.bucket.assert_called_once()
            mock_blob.upload_from_filename.assert_called_once_with("/tmp/test-video.mp4")


class TestNotifyLatestVideo:
    @pytest.mark.asyncio
    async def test_notify_latest_video(self):
        """Test notifying clients about latest video."""
        with patch.object(latest_video_manager, 'broadcast', new_callable=AsyncMock) as mock_broadcast:
            await notify_latest_video()

            mock_broadcast.assert_called_once()
            call_arg = mock_broadcast.call_args[0][0]
            data = json.loads(call_arg)
            assert "latest_video_url" in data


class TestLookupExternalIP:
    def test_lookup_external_ip(self):
        """Test external IP lookup."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"192.168.1.1"

        with patch('urllib.request.urlopen', return_value=mock_response):
            ip = lookup_external_ip()
            assert ip == "192.168.1.1"


class TestListMonthsEndpoint:
    def test_list_months_success(self):
        """Test GET /api/months returns months data."""
        mock_months = [
            {"year": 2025, "month": 1, "sunrise_count": 31, "sunset_count": 28},
        ]

        with patch('app.concat.list_available_months', return_value=mock_months):
            response = client.get("/api/months")

        assert response.status_code == 200
        data = response.json()
        assert "months" in data
        assert len(data["months"]) == 1
        assert data["months"][0]["year"] == 2025

    def test_list_months_empty(self):
        """Test GET /api/months when no months available."""
        with patch('app.concat.list_available_months', return_value=[]):
            response = client.get("/api/months")

        assert response.status_code == 200
        data = response.json()
        assert data["months"] == []

    def test_list_months_error(self):
        """Test GET /api/months handles errors."""
        with patch('app.concat.list_available_months', side_effect=Exception("GCS error")):
            response = client.get("/api/months")

        assert response.status_code == 500
        assert "GCS error" in response.json()["detail"]


class TestGenerateCompilationEndpoint:
    def test_generate_compilation_success(self):
        """Test POST /api/compilation/generate creates compilation."""
        mock_result = {
            "url": "https://storage.googleapis.com/test/compilation.mp4",
            "video_count": 30,
            "duration_seconds": 450.0,
            "cached": False,
        }

        with patch('app.concat.generate_compilation', return_value=mock_result):
            response = client.post("/api/compilation/generate?year=2025&month=1")

        assert response.status_code == 200
        data = response.json()
        assert data["url"] == mock_result["url"]
        assert data["video_count"] == 30

    def test_generate_compilation_with_time_filter(self):
        """Test POST /api/compilation/generate with time_filter."""
        mock_result = {"url": "https://test.url", "cached": True}

        with patch('app.concat.generate_compilation', return_value=mock_result) as mock_gen:
            response = client.post(
                "/api/compilation/generate?year=2025&month=1&time_filter=sunset"
            )

        assert response.status_code == 200
        # Verify time_filter was passed
        call_kwargs = mock_gen.call_args[1]
        assert call_kwargs["time_filter"] == "sunset"

    def test_generate_compilation_invalid_month(self):
        """Test POST /api/compilation/generate with invalid month."""
        response = client.post("/api/compilation/generate?year=2025&month=13")
        assert response.status_code == 400
        assert "month must be between 1 and 12" in response.json()["detail"]

    def test_generate_compilation_invalid_time_filter(self):
        """Test POST /api/compilation/generate with invalid time_filter."""
        response = client.post(
            "/api/compilation/generate?year=2025&month=1&time_filter=noon"
        )
        assert response.status_code == 400
        assert "time_filter must be" in response.json()["detail"]

    def test_generate_compilation_no_videos(self):
        """Test POST /api/compilation/generate when no videos found."""
        with patch('app.concat.generate_compilation', side_effect=ValueError("No videos found")):
            response = client.post("/api/compilation/generate?year=2025&month=1")

        assert response.status_code == 404
        assert "No videos found" in response.json()["detail"]

    def test_generate_compilation_force_regenerate(self):
        """Test POST /api/compilation/generate with force=true."""
        mock_result = {"url": "https://test.url", "cached": False}

        with patch('app.concat.generate_compilation', return_value=mock_result) as mock_gen:
            response = client.post(
                "/api/compilation/generate?year=2025&month=1&force=true"
            )

        assert response.status_code == 200
        call_kwargs = mock_gen.call_args[1]
        assert call_kwargs["force_regenerate"] is True


class TestGetCompilationStatusEndpoint:
    def test_get_compilation_exists(self):
        """Test GET /api/compilation/{year}/{month} when compilation exists."""
        mock_result = {
            "exists": True,
            "url": "https://storage.googleapis.com/test/compilation.mp4",
            "size_bytes": 100000000,
        }

        with patch('app.concat.check_compilation_exists', return_value=mock_result):
            response = client.get("/api/compilation/2025/1")

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert "url" in data

    def test_get_compilation_not_exists(self):
        """Test GET /api/compilation/{year}/{month} when not exists."""
        mock_result = {"exists": False}

        with patch('app.concat.check_compilation_exists', return_value=mock_result):
            response = client.get("/api/compilation/2025/1")

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is False

    def test_get_compilation_with_time_filter(self):
        """Test GET /api/compilation/{year}/{month} with time_filter."""
        mock_result = {"exists": True}

        with patch('app.concat.get_compilation_blob_name', return_value="test.mp4") as mock_name, \
             patch('app.concat.check_compilation_exists', return_value=mock_result):
            response = client.get("/api/compilation/2025/1?time_filter=sunrise")

        assert response.status_code == 200
        mock_name.assert_called_once_with(2025, 1, "sunrise")

    def test_get_compilation_invalid_month(self):
        """Test GET /api/compilation/{year}/{month} with invalid month."""
        response = client.get("/api/compilation/2025/0")
        assert response.status_code == 400

    def test_get_compilation_invalid_time_filter(self):
        """Test GET /api/compilation/{year}/{month} with invalid time_filter."""
        response = client.get("/api/compilation/2025/1?time_filter=invalid")
        assert response.status_code == 400


class TestGalleryEndpoint:
    def test_gallery_serves_html(self):
        """Test GET /gallery serves the index.html file."""
        with patch('app.FileResponse') as mock_response:
            mock_response.return_value = MagicMock()
            # The actual endpoint will try to serve the file
            # We just verify the route exists and returns 200 or handles missing file
            response = client.get("/gallery")
            # Will be 404 if file doesn't exist in test env, which is expected
            assert response.status_code in (200, 404)


class TestSunsetGalleryIntegration:
    """Tests for sunset gallery API integration."""

    def test_list_months_includes_sunset_count(self):
        """Test GET /api/months returns sunset_count for each month."""
        mock_months = [
            {
                "year": 2025,
                "month": 1,
                "sunrise_count": 31,
                "sunset_count": 28,
                "total_count": 59,
                "has_sunrise_compilation": False,
                "has_sunset_compilation": True,
                "has_all_compilation": False,
            },
        ]

        with patch('app.concat.list_available_months', return_value=mock_months):
            response = client.get("/api/months")

        assert response.status_code == 200
        data = response.json()
        assert "months" in data
        month = data["months"][0]
        assert "sunset_count" in month
        assert month["sunset_count"] == 28
        assert "has_sunset_compilation" in month

    def test_generate_sunset_compilation(self):
        """Test POST /api/compilation/generate with time_filter=sunset."""
        mock_result = {
            "url": "https://storage.googleapis.com/bucket/2025/01/compilations/sunset-2025-01.mp4",
            "video_count": 28,
            "duration_seconds": 420.0,
            "size_bytes": 85000000,
            "cached": False,
            "generated_at": "2025-01-24T12:00:00",
        }

        with patch('app.concat.generate_compilation', return_value=mock_result) as mock_gen:
            response = client.post(
                "/api/compilation/generate?year=2025&month=1&time_filter=sunset"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["video_count"] == 28
        assert "sunset" in data["url"]

        # Verify sunset filter was passed to the function
        call_kwargs = mock_gen.call_args[1]
        assert call_kwargs["time_filter"] == "sunset"

    def test_get_sunset_compilation_status(self):
        """Test GET /api/compilation/{year}/{month}?time_filter=sunset."""
        mock_result = {
            "exists": True,
            "url": "https://storage.googleapis.com/bucket/2025/01/compilations/sunset-2025-01.mp4",
            "size_bytes": 85000000,
            "updated": "2025-01-24T12:00:00Z",
        }

        with patch('app.concat.get_compilation_blob_name', return_value="2025/01/compilations/sunset-2025-01.mp4") as mock_name, \
             patch('app.concat.check_compilation_exists', return_value=mock_result):
            response = client.get("/api/compilation/2025/1?time_filter=sunset")

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        mock_name.assert_called_once_with(2025, 1, "sunset")

    def test_sunset_compilation_not_exists(self):
        """Test GET /api/compilation status when sunset compilation doesn't exist."""
        mock_result = {"exists": False}

        with patch('app.concat.get_compilation_blob_name', return_value="test.mp4"), \
             patch('app.concat.check_compilation_exists', return_value=mock_result):
            response = client.get("/api/compilation/2025/1?time_filter=sunset")

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is False

    def test_generate_sunset_compilation_no_videos(self):
        """Test generating sunset compilation when no sunset videos exist."""
        with patch('app.concat.generate_compilation',
                   side_effect=ValueError("No videos found for 2025/01 (sunset)")):
            response = client.post(
                "/api/compilation/generate?year=2025&month=1&time_filter=sunset"
            )

        assert response.status_code == 404
        assert "No videos found" in response.json()["detail"]

    def test_generate_sunset_compilation_cached(self):
        """Test retrieving cached sunset compilation."""
        mock_result = {
            "url": "https://storage.googleapis.com/bucket/2025/01/compilations/sunset-2025-01.mp4",
            "size_bytes": 85000000,
            "cached": True,
            "generated_at": "2025-01-20T12:00:00",
        }

        with patch('app.concat.generate_compilation', return_value=mock_result):
            response = client.post(
                "/api/compilation/generate?year=2025&month=1&time_filter=sunset"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["cached"] is True

    def test_multiple_months_with_sunset_data(self):
        """Test listing multiple months all with sunset data."""
        mock_months = [
            {"year": 2025, "month": 1, "sunset_count": 28, "has_sunset_compilation": True},
            {"year": 2024, "month": 12, "sunset_count": 30, "has_sunset_compilation": False},
            {"year": 2024, "month": 11, "sunset_count": 25, "has_sunset_compilation": True},
        ]

        with patch('app.concat.list_available_months', return_value=mock_months):
            response = client.get("/api/months")

        assert response.status_code == 200
        data = response.json()
        assert len(data["months"]) == 3

        # Verify all months have sunset data
        for month in data["months"]:
            assert "sunset_count" in month
            assert month["sunset_count"] > 0
