from app import app, active_jobs, get_active_jobs, run_async_subprocess
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
import asyncio
import unittest
import uuid

# Mock process to simulate subprocess behavior with a delay
class MockProcess:
    def __init__(self):
        self.stdout = AsyncMock()
        self.stderr = AsyncMock()
        self.returncode = 0  # Simulate a successful process

    async def communicate(self):
        # Simulate a process running for 10 seconds
        await asyncio.sleep(10)
        return (b"Mocked stdout output", b"Mocked stderr output")

    def kill(self):
        pass

    async def wait(self):
        pass

class TestCameraCollectorService(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

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
        self.assertTrue(data["job_id"] in active_jobs)
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

    @patch("asyncio.create_subprocess_exec", return_value=MockProcess())
    def test_run_async_subprocess(self, mock_subprocess_exec):
        """Test running a collection job with a mocked subprocess."""
        job_id = "mock-job-id"

        # Run the asynchronous function
        asyncio.run(run_async_subprocess(job_id))

        # Validate interactions with the mocked subprocess
        mock_subprocess_exec.assert_called_once_with(
            "./gcloud_upload.sh",  # Replace with your actual command
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        asyncio.sleep(11)
        # Verify the job status update
        self.assertEqual(active_jobs[job_id], "completed")

if __name__ == "__main__":
    unittest.main()
