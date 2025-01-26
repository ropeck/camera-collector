import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from app import collect_and_upload_video, active_jobs, app
from fastapi.testclient import TestClient
import uuid
from datetime import datetime

client = TestClient(app)

@pytest.mark.asyncio
class TestCameraCollector:

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup and teardown for tests."""
        active_jobs.data.clear()
        yield

    async def test_root_endpoint(self):
        """Test the root endpoint to check API status and version."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "version" in data

    async def test_start_collection(self):
        """Test starting a collection job."""
        youtube_url = "https://www.youtube.com/watch?v=example"
        response = client.post(f"/collection/start/{youtube_url}")
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert "message" in data

        job_id = data["job_id"]
        job_info = await active_jobs.get_job(job_id)
        assert job_info is not None
        assert job_info["url"] == youtube_url
        assert job_info["status"] == "running"

    async def test_collection_status_valid_job(self):
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
        assert data["job_id"] == job_id
        assert data["url"] == "https://www.youtube.com/watch?v=example"
        assert data["status"] == "running"

    async def test_collection_status_invalid_job(self):
        """Test retrieving the status of an invalid job ID."""
        job_id = str(uuid.uuid4())

        response = client.get(f"/collection/status/{job_id}")
        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Job ID not found."

    async def test_active_collections(self):
        """Test retrieving the list of active collections."""
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
            "status": "running",
        })

        response = client.get("/active-collections")
        assert response.status_code == 200
        data = response.json()
        assert "active_jobs" in data

        active_jobs_data = data["active_jobs"]
        assert job_id1 in active_jobs_data
        assert job_id2 in active_jobs_data
        assert active_jobs_data[job_id1]["url"] == "https://www.youtube.com/watch?v=example1"
        assert active_jobs_data[job_id2]["url"] == "https://www.youtube.com/watch?v=example2"
