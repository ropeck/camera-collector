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
import pytest
from unittest.mock import AsyncMock, patch

app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

BUILD_TIME = os.getenv("BUILD_TIME")
SERVER_START_TIME = datetime.now().isoformat()

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
active_jobs = defaultdict(str)

# Initialize Google Cloud Storage client
storage_client = storage.Client.from_service_account_json('/app/service-account-key.json')
bucket_name = "fogcat-webcam"

def get_active_jobs():
    return active_jobs


async def collect_and_upload_video(job_id: str):
    try:
        active_jobs[job_id] = "running"
        logging.info(f"Job {job_id} started.")
        await manager.send_message(job_id, f"Job {job_id} started.")

        video_path = "/app/video.mp4"
        youtube_url = "https://www.youtube.com/watch?v=example"  # Replace with the desired URL

        # Download video using yt-dlp
        logging.info(f"Starting video download from {youtube_url}...")
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',  # Best quality
            'outtmpl': video_path,  # Output path
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4'  # Convert to mp4
            }],
            'download_ranges': [
                {'start_time': 0, 'end_time': 15}  # Download only the first 15 seconds
            ]
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])

        # Ensure video file exists
        if not os.path.exists(video_path):
            raise FileNotFoundError("Video file was not created.")

        logging.info("Video download complete.")

        # Upload video to GCS
        upload_to_gcs(video_path)

        # Clean up
        os.remove(video_path)

        await manager.send_message(job_id, f"Job {job_id} completed successfully.")
        active_jobs[job_id] = "completed"
        logging.info(f"Job {job_id} completed successfully.")
    except Exception as e:
        error_message = str(e)
        await manager.send_message(job_id, f"Error in Job {job_id}: {error_message}")
        active_jobs[job_id] = "error"
        logging.error(f"Error in Job {job_id}: {error_message}")
    finally:
        # Cleanup active job
        if job_id in active_jobs:
            del active_jobs[job_id]


def upload_to_gcs(video_path: str):
    """
    Uploads a video to Google Cloud Storage.
    """
    bucket = storage_client.bucket(bucket_name)
    timestamp_path = datetime.now().strftime("%Y/%m")
    video_name = os.path.basename(video_path)
    blob_name = f"{timestamp_path}/{video_name}"
    blob = bucket.blob(blob_name)

    logging.info(f"Uploading {video_path} to {blob_name} in bucket {bucket_name}...")
    blob.upload_from_filename(video_path)
    logging.info(f"File uploaded to GCS successfully at {blob_name}.")


@app.get("/")
async def root():
    version_info = ("BUILD_TIME: " + BUILD_TIME) if BUILD_TIME else ("SERVER_START_TIME: " + SERVER_START_TIME)
    return JSONResponse({"message": "Camera Collector API is running!", "version": version_info})


@app.post("/collection/start")
async def start_collection():
    job_id = str(uuid.uuid4())
    asyncio.create_task(collect_and_upload_video(job_id))
    logging.info(f"Collection started with Job ID: {job_id}")
    return JSONResponse({"job_id": job_id, "message": f"Collection started with Job ID {job_id}"})


@app.get("/collection/status/{job_id}")
async def collection_status(job_id: str):
    if job_id in active_jobs:
        status = active_jobs[job_id]
        logging.info(f"Status for Job ID {job_id}: {status}")
        return JSONResponse({"job_id": job_id, "status": status})
    else:
        logging.warning(f"Job ID {job_id} not found.")
        raise HTTPException(status_code=404, detail="Job ID not found.")


@app.get("/active-collections")
async def get_active_collections():
    logging.info("Fetching active collections.")
    return JSONResponse({"active_jobs": active_jobs})


@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    await manager.connect(websocket, job_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(job_id)
        logging.info(f"WebSocket connection closed for Job ID: {job_id}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
