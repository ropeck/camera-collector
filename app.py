import asyncio
import os
import logging
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
import uuid
from datetime import datetime
from google.cloud import storage
import yt_dlp
import subprocess
import traceback
from typing import Optional

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
from collections import UserDict

class ThreadSafeJobs(UserDict):
    def __init__(self):
        super().__init__()
        self._lock = asyncio.Lock()

    async def set_status(self, job_id: str, status: str):
        """Safely set the status of a job."""
        async with self._lock:
            if job_id in self.data:
                self.data[job_id]["status"] = status

    async def set_job(self, job_id: str, job_info: dict):
        async with self._lock:
            self.data[job_id] = job_info

    async def get_job(self, job_id: str):
        async with self._lock:
            return self.data.get(job_id)

    async def delete_job(self, job_id: str):
        async with self._lock:
            if job_id in self.data:
                del self.data[job_id]

    async def get_all_jobs(self):
        async with self._lock:
            return {job_id: job_info for job_id, job_info in self.data.items()}

active_jobs = ThreadSafeJobs()

# Initialize Google Cloud Storage client
storage_client = storage.Client.from_service_account_json(SERVICE_ACCOUNT_FILE)


def download_video(youtube_url: str, output_path: str):
    """
    Downloads a video from YouTube using yt-dlp.
    """
    logging.info(f"Starting video download from {youtube_url}...")

    # yt-dlp options for live streaming
    ydl_opts = {
        "format": "best",  # Choose the best available format
        "outtmpl": "-",  # Output to stdout for piping
        "quiet": True  # Suppress yt-dlp logs
    }

    # Start ffmpeg process
    ffmpeg_process = subprocess.Popen(
        [
            "ffmpeg",
            "-i", "pipe:0",  # Input from stdin
            "-t", "15",  # Limit duration to 15 seconds
            "-c:v", "libx264",
            "-c:a", "aac",
            "-movflags", "+faststart",
            output_path
        ],
        stdin=subprocess.PIPE,  # ffmpeg reads from stdin
        stdout=subprocess.PIPE,  # Optional: capture ffmpeg's output
        stderr=subprocess.PIPE  # Capture ffmpeg's errors
    )

    # Use yt-dlp to fetch the live stream and pipe its output to ffmpeg
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        def download_and_pipe():
            ydl.download([youtube_url])

        # Redirect yt-dlp's output to ffmpeg's stdin
        download_process = subprocess.Popen(
            ["yt-dlp", "--no-warnings", "-f", "best", "-o", "-", youtube_url],
            stdout=ffmpeg_process.stdin,
            stderr=subprocess.PIPE
        )

        download_process.wait()

    # Close ffmpeg's input and wait for it to finish
    ffmpeg_process.stdin.close()
    ffmpeg_process.wait()

    # Check for errors
    if ffmpeg_process.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {ffmpeg_process.stderr.read().decode()}")


def process_video_with_ffmpeg(input_path: str, output_path: str):
    """
    Processes the video using FFmpeg to ensure compatibility with Safari.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file {input_path} does not exist.")

    logging.info(f"Processing video {input_path} with FFmpeg...")
    command = [
        "ffmpeg",
        "-i", input_path,  # Input file
        "-c:v", "libx264",  # Use H.264 video codec
        "-c:a", "aac",  # Use AAC audio codec
        "-movflags", "+faststart",  # Enable progressive streaming
        "-y",  # Overwrite output file if it exists
        output_path  # Output file
    ]

    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.returncode != 0:
        logging.error(f"FFmpeg processing failed: {process.stderr.decode()}")
        raise RuntimeError(f"FFmpeg processing failed: {process.stderr.decode()}")

    logging.info(f"Video processed successfully: {output_path}")


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


async def collect_and_upload_video(job_id: str, youtube_url: str):
    ffmpeg_process = None
    output_path = "output_live.mp4"

    try:
        await active_jobs.set_job(job_id, {
            "url": youtube_url,
            "time_started": datetime.now().isoformat(),
            "status": "running",
        })
        logging.info(f"Job {job_id} started.")
        await manager.send_message(job_id, f"Job {job_id} started.")

        raw_video_path = f"/app/raw_video_{job_id}.mp4"
        processed_video_path = f"/app/video_{job_id}.mp4"

        # Download video
        ydl_opts = {
            "format": "best",  # Choose the best available format
            "outtmpl": "-",    # Output to stdout for piping
            "quiet": True      # Suppress yt-dlp logs
        }

        # Start the FFmpeg process
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", "pipe:0",  # Input from stdin
            "-t", "15",      # Limit duration to 15 seconds
            "-c:v", "libx264",
            "-c:a", "aac",
            "-movflags", "+faststart",
            output_path
        ]

        # Run FFmpeg in an asynchronous subprocess
        ffmpeg_process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Use yt-dlp to fetch the live stream and pipe its output to ffmpeg
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            async with asyncio.subprocess.create_subprocess_exec(
                "yt-dlp", "--no-warnings", "-f", "best", "-o", "-", youtube_url,
                stdout=ffmpeg_process.stdin,
                stderr=asyncio.subprocess.PIPE
            ) as yt_dlp_process:
                await yt_dlp_process.wait()

        # Close FFmpeg's stdin to signal completion
        if ffmpeg_process.stdin:
            ffmpeg_process.stdin.close()

        # Wait for FFmpeg to finish processing
        await ffmpeg_process.wait()

        # Check for errors
        stderr = await ffmpeg_process.stderr.read()
        if ffmpeg_process.returncode != 0:
            raise RuntimeError(f"FFmpeg error: {stderr.decode()}")

    except Exception as e:
        raise RuntimeError(f"Error during video collection: {e}")

    finally:
        # Ensure FFmpeg is terminated
        if ffmpeg_process:
            ffmpeg_process.terminate()

@app.get("/")
async def root():
    version_info = ("BUILD_TIME: " + BUILD_TIME) if BUILD_TIME else ("SERVER_START_TIME: " + SERVER_START_TIME)
    return JSONResponse({"message": "Camera Collector API is running!", "version": version_info})

@app.post("/collection/start/{youtube_url:path}")
async def start_collection(youtube_url: Optional[str] = None):
    """
    Starts a new collection job using the given YouTube URL or the default URL.
    """
    youtube_url = youtube_url or DEFAULT_YOUTUBE_URL

    job_id = str(uuid.uuid4())
    asyncio.create_task(collect_and_upload_video(job_id, youtube_url))
    logging.info(f"Collection started with Job ID: {job_id}")
    return JSONResponse({"job_id": job_id, "message": f"Collection started with Job ID {job_id}"})


@app.post("/collection/start")
async def start_collection_root(request: Request, youtube_url: Optional[str] = None):
    """
    Redirects to the /collection/start/{youtube_url:path} with the default YouTube URL if none is provided.
    """
    youtube_url = DEFAULT_YOUTUBE_URL

    job_id = str(uuid.uuid4())
    asyncio.create_task(collect_and_upload_video(job_id, youtube_url))
    logging.info(f"Collection started with Job ID: {job_id}")
    return JSONResponse({"job_id": job_id, "message": f"Collection started with Job ID {job_id}"})



@app.get("/collection/status/{job_id}")
async def collection_status(job_id: str):
    """
    Retrieve the status of a specific job ID.
    """
    job_info = await active_jobs.get_job(job_id)
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
    active_job_info = await active_jobs.get_all_jobs()
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
