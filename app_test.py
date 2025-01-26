import asyncio
import uuid
from unittest import TestCase
from unittest.mock import AsyncMock, patch
from app import collect_and_upload_video, bucket_name, app, active_jobs
from fastapi.testclient import TestClient

class TestCameraCollector(TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_collect_and_upload_video(self):
        """Unit test for collect_and_upload_video function."""
        job_id = "test-job-id"

        # Mock yt-dlp and Google Cloud Storage
        with patch("yt_dlp.YoutubeDL") as mock_yt, patch("google.cloud.storage.Client") as mock_storage:
            # Mock download method in yt-dlp
            mock_yt.return_value.__enter__.return_value.download = AsyncMock()

            # Mock GCS upload method
            mock_storage.return_value.bucket.return_value.blob.return_value.upload_from_filename = AsyncMock()

            # Run the function asynchronously
            asyncio.run(collect_and_upload_video(job_id))

            # Assertions to ensure methods were called as expected
            mock_yt.return_value.__enter__.return_value.download.assert_called_once()
            mock_storage.return_value.bucket.assert_called_once_with(bucket_name)
            mock_storage.return_value.bucket.return_value.blob.return_value.upload_from_filename.assert_called_once()
            print("Test passed: collect_and_upload_video.")

    def test_root_endpoint(self):
        """Test the root endpoint to check API status and version."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("message", data)
        self.assertIn("version", data)

    def test_start_collection(self):
        """Test starting a collection job."""
        response = self.client.post("/collection/start")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("job_id", data)
        self.assertIn("message", data)
        self.assertIn(data["job_id"], active_jobs)
        self.assertEqual(active_jobs[data["job_id"]], "running")

    def test_collection_status_valid_job(self):
        """Test retrieving the status of a valid job ID."""
        job_id = str(uuid.uuid4())
        active_jobs[job_id] = "running"

        response = self.client.get(f"/collection/status/{job_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["job_id"], job_id)
        self.assertEqual(data["status"], "running")

    def test_collection_status_invalid_job(self):
        """Test retrieving the status of an invalid job ID."""
        job_id = str(uuid.uuid4())

        response = self.client.get(f"/collection/status/{job_id}")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["detail"], "Job ID not found.")

    def test_active_collections(self):
        """Test retrieving the list of active collections."""
        job_id1 = str(uuid.uuid4())
        job_id2 = str(uuid.uuid4())
        active_jobs[job_id1] = "running"
        active_jobs[job_id2] = "running"

        response = self.client.get("/active-collections")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("active_jobs", data)
        self.assertIn(job_id1, data["active_jobs"])
        self.assertIn(job_id2, data["active_jobs"])
