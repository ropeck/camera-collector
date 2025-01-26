import asyncio
import os
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
import uuid
from datetime import datetime
from collections import defaultdict
from pathlib import Path
from google.cloud import storage
import yt_dlp

app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

BUILD_TIME = os.getenv("BUILD_TIME")
SERVER_START_TIME = datetime.now().isoformat()

BUCKET_NAME = os.getenv("BUCKET_NAME", "fogcat-webcam")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "/app/service-account-key.json")
DEFAULT_YOUTUBE_URL = os.getenv("DEFAULT_YOUTUBE_URL", "https://www.youtube.com/watch?v=hXtYKDio1rQ")

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, job_id: str):
        await websocket.accept()
        self.active_connections[job_id] = websocket
        logging.info(f"WebSocket connection established for Job ID: {job_id}")

    def disconnect(self, job_id: str):
        if job_id in self.active_connections:
            del self.active_connections[job_id]
            logging.info(f"WebSocket connection closed for Job ID: {job_id}")

    async def send_message(self, job_id: str, message: str):
        if job_id in self.active_connections:
            try:
                await self.active_connections[job_id].send_text(message)
                logging.info(f"Message sent to Job ID {job_id}: {message}")
            except Exception as e:
                logging.error(f"Failed to send message to Job ID {job_id}: {str(e)}")


manager = ConnectionManager()
active_jobs = {}

# Initialize Google Cloud Storage client
storage_client = storage.Client.from_service_account_json(SERVICE_ACCOUNT_FILE)

def get_active_jobs():
    return active_jobs


def download_video(youtube_url: str, output_path: str):
    """
    Downloads a video from YouTube using yt-dlp.
    """
    logging.info(f"Starting video download from {youtube_url}...")
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': output_path,
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4'
        }],
        'download_ranges': [
            {'start_time': 0, 'end_time': 15}
        ]
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([youtube_url])


def upload_to_gcs(video_path: str):
    """
    Uploads a video to Google Cloud Storage.
    """
    bucket = storage_client.bucket(BUCKET_NAME)
    timestamp_path = datetime.now().strftime("%Y/%m")
    video_name = os.path.basename(video_path)
    blob_name = f"{timestamp_path}/{video_name}"
    blob = bucket.blob(blob_name)

    logging.info(f"Uploading {video_path} to {blob_name} in bucket {BUCKET_NAME}...")
    blob.upload_from_filename(video_path)
    logging.info(f"File uploaded to GCS successfully at {blob_name}.")


def format_job_info(job_id: str):
    """Formats job information for API responses."""
    job_info = active_jobs.get(job_id, None)
    if not job_info:
        return None
    return {
        "job_id": job_id,
        "url": job_info.get("url"),
        "time_started": job_info.get("time_started"),
        "status": job_info.get("status"),
    }


async def collect_and_upload_video(job_id: str, youtube_url: str):
    try:
        active_jobs[job_id] = {
            "url": youtube_url,
            "time_started": datetime.now().isoformat(),
            "status": "running",
        }
        logging.info(f"Job {job_id} started.")
        await manager.send_message(job_id, f"Job {job_id} started.")

        video_path = f"/app/video_{job_id}.mp4"
        download_video(youtube_url, video_path)

        # Ensure video file exists
        if not os.path.exists(video_path):
            raise FileNotFoundError("Video file was not created.")

        logging.info("Video download complete.")

        upload_to_gcs(video_path)

        # Clean up
        os.remove(video_path)

        active_jobs[job_id]["status"] = "completed"
        await manager.send_message(job_id, f"Job {job_id} completed successfully.")
        logging.info(f"Job {job_id} completed successfully.")
    except Exception as e:
        error_message = str(e)
        active_jobs[job_id]["status"] = "error"
        await manager.send_message(job_id, f"Error in Job {job_id}: {error_message}")
        logging.error(f"Error in Job {job_id}: {error_message}")
    finally:
        # Cleanup active job
        if job_id in active_jobs and active_jobs[job_id]["status"] == "completed":
            del active_jobs[job_id]


@app.get("/")
async def root():
    version_info = ("BUILD_TIME: " + BUILD_TIME) if BUILD_TIME else ("SERVER_START_TIME: " + SERVER_START_TIME)
    return JSONResponse({"message": "Camera Collector API is running!", "version": version_info})


@app.post("/collection/start")
async def start_collection(youtube_url: str = DEFAULT_YOUTUBE_URL):
    """
    Starts a new collection job using the given YouTube URL or the default URL.
    """
    job_id = str(uuid.uuid4())
    asyncio.create_task(collect_and_upload_video(job_id, youtube_url))
    logging.info(f"Collection started with Job ID: {job_id}")
    return JSONResponse({"job_id": job_id, "message": f"Collection started with Job ID {job_id}"})


@app.get("/collection/status/{job_id}")
async def collection_status(job_id: str):
    """
    Retrieve the status of a specific job ID.
    """
    job_info = format_job_info(job_id)
    if not job_info:
        logging.warning(f"Job ID {job_id} not found.")
        raise HTTPException(status_code=404, detail="Job ID not found.")
    logging.info(f"Status for Job ID {job_id}: {job_info}")
    return JSONResponse(job_info)


@app.get("/active-collections")
async def get_active_collections():
    """
    Retrieve the list of currently active collection job IDs.
    """
    logging.info("Fetching active collections.")
    active_job_info = {job_id: format_job_info(job_id) for job_id in active_jobs}
    return JSONResponse({"active_jobs": active_job_info})


@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """
    WebSocket connection for real-time notifications for a specific job.
    """
    await manager.connect(websocket, job_id)
    try:
        while True:
            # Keep the connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(job_id)
        logging.info(f"WebSocket connection closed for Job ID: {job_id}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
