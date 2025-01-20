import unittest
from fastapi.testclient import TestClient
from app import app, active_jobs
import asyncio
import uuid

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
        print(f"data: {data}")
        print(f"active_jobs: {active_jobs}")
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

    def test_websocket_connection(self):
        """Test WebSocket connection for real-time job notifications."""
        response = self.client.post("/collection/start")
        data = response.json()
        job_id = data["job_id"]
        with self.client.websocket_connect(f"/ws/{job_id}") as websocket:
            websocket.send_text("ping")
            self.assertTrue(job_id in active_jobs)
            websocket.close()
            self.assertNotIn(job_id, active_jobs)

if __name__ == "__main__":
    unittest.main()
