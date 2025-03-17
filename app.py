import json
from collections import UserDict
from datetime import datetime
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
from google.cloud import storage
from typing import Optional
import asyncio
import logging
import os
import subprocess
import traceback
import uuid

app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

BUILD_TIME = os.getenv("BUILD_TIME")
SERVER_START_TIME = datetime.now().isoformat()

BUCKET_NAME = os.getenv("BUCKET_NAME", "fogcat-webcam")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "/app/service-account-key.json")
DEFAULT_YOUTUBE_URL = os.getenv("DEFAULT_YOUTUBE_URL", "https://www.youtube.com/watch?v=hXtYKDio1rQ")


# WebSocket connection manager for job-specific updates
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


# WebSocket connection manager for broadcasting latest video updates
class LatestVideoConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logging.info("WebSocket client connected for latest video updates.")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logging.info("WebSocket client disconnected from latest video updates.")

    async def broadcast(self, message: str):
        logging.info(f"Broadcasting message to {len(self.active_connections)} clients: {message}")
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logging.error(f"Error sending message to WebSocket client: {e}")
                self.disconnect(connection)


latest_video_manager = LatestVideoConnectionManager()


class ThreadSafeJobs(UserDict):
    def __init__(self):
        super().__init__()
        self._lock = asyncio.Lock()

    async def set_status(self, job_id: str, status: str):
        """Safely set the status of a job."""
        async with self._lock:
            if job_id in self.data:
                self.data[job_id]["status"] = status
        await manager.send_message(job_id,
                                   json.dumps({"job_id": job_id,
                                               "status": status}))

    async def set_job(self, job_id: str, job_info: dict):
        async with self._lock:
            self.data[job_id] = job_info
        await manager.send_message(job_id,
                                   json.dumps({"job_id": job_id,
                                               "job_info": job_info}))

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


def run_subprocess_blocking(youtube_url, output_path):
    """
    Runs the blocking subprocess operations for yt-dlp and FFmpeg.
    """
    ffmpeg_process = None
    yt_dlp_process = None

    # FFmpeg command to capture 15 seconds
    ffmpeg_cmd = [
        "ffmpeg",
        "-i", "pipe:0",  # Input from stdin
        "-t", "15",      # Limit duration to 15 seconds
        "-c:v", "libx264",
        "-c:a", "aac",
        "-movflags", "+faststart",
        output_path
    ]
    logging.info("command: " + " ".join(ffmpeg_cmd))

    # get available formats with --list-formats
    # $ yt-dlp -f best -o foo 'https://www.youtube.com/watch?v=hXtYKDio1rQ' --list-formats
    # WARNING: "-f best" selects the best pre-merged format which is often not the best option.
    #          To let yt-dlp download and merge the best available formats, simply do not pass any format selection.
    #          If you know what you are doing and want only the best pre-merged format, use "-f b" instead to suppress this warning
    # [youtube] Extracting URL: https://www.youtube.com/watch?v=hXtYKDio1rQ
    # [youtube] hXtYKDio1rQ: Downloading webpage
    # [youtube] hXtYKDio1rQ: Downloading ios player API JSON
    # [youtube] hXtYKDio1rQ: Downloading web creator player API JSON
    # [youtube] hXtYKDio1rQ: Downloading m3u8 information
    # [info] Available formats for hXtYKDio1rQ:
    # ID  EXT RESOLUTION FPS │   TBR PROTO │ VCODEC        VBR ACODEC     MORE INFO
    # ─────────────────────────────────────────────────────────────────────────────
    # 233 mp4 audio only     │       m3u8  │ audio only        unknown    Default
    # 234 mp4 audio only     │       m3u8  │ audio only        unknown    Default
    # 269 mp4 256x144     30 │  269k m3u8  │ avc1.4D400C  269k video only
    # 229 mp4 426x240     30 │  507k m3u8  │ avc1.4D4015  507k video only
    # 230 mp4 640x360     30 │  962k m3u8  │ avc1.4D401E  962k video only
    # 231 mp4 854x480     30 │ 1283k m3u8  │ avc1.4D401F 1283k video only
    # 232 mp4 1280x720    30 │ 2448k m3u8  │ avc1.4D401F 2448k video only
    # cmd = ["yt-dlp", "-f", "best", "-o", "-", youtube_url]
    cmd = ["curl", "ifconfig.me"]
    logging.info("# " + " ".join(cmd))
    result = subprocess.run(cmd)
    logging.info("> " + result.stdout)

    cmd = ["yt-dlp", "-o", "-", youtube_url]
    logging.info("command: " + " ".join(cmd))

    try:
        # Start FFmpeg in a subprocess
        ffmpeg_process = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # Start yt-dlp and pipe its output to FFmpeg
        yt_dlp_process = subprocess.Popen(
            cmd,
            stdout=ffmpeg_process.stdin,
            stderr=subprocess.PIPE
        )

        # Wait for FFmpeg to finish processing
        ffmpeg_process.communicate()  # Block until FFmpeg is done

        # Terminate yt-dlp after FFmpeg finishes its duration
        yt_dlp_process.terminate()
        yt_dlp_process.wait()

        # Check FFmpeg's return code
        if ffmpeg_process.returncode != 0:
            stderr = ffmpeg_process.stderr.read().decode()
            raise RuntimeError(f"FFmpeg error: {stderr}")
    finally:
        # Ensure FFmpeg and yt-dlp are terminated
        if ffmpeg_process and ffmpeg_process.poll() is None:
            ffmpeg_process.terminate()
        if yt_dlp_process and yt_dlp_process.poll() is None:
            yt_dlp_process.terminate()


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


async def notify_latest_video():
    """
    Notify all WebSocket clients about the latest video URL.
    """
    latest_video_url = "https://weather.fogcat5.com/collector/video_latest"
    message = json.dumps({"latest_video_url": latest_video_url})
    await latest_video_manager.broadcast(message)


async def collect_and_upload_video(job_id: str, youtube_url: str):
    """
    Asynchronously collect and upload video by offloading blocking tasks.
    """
    await active_jobs.set_status(job_id, "in progress")
    local_time = datetime.now().astimezone()
    timestamp = local_time.strftime('%Y-%m-%dT%H:%M-%S%z')
    output_path = f"/app/seacliff-{timestamp}.mp4"
    try:
        # Offload the blocking subprocess call to a separate thread
        await asyncio.to_thread(run_subprocess_blocking, youtube_url, output_path)

        # Upload the video to GCS
        await active_jobs.set_status(job_id, "uploading to gcs")
        await asyncio.to_thread(upload_to_gcs, output_path)

        # Notify WebSocket clients about the latest video
        await notify_latest_video()

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"{str(e)}{tb}"
        logging.error(f"Error during video collection: {error_message}")
        await active_jobs.set_status(job_id, "error")
        raise RuntimeError(f"Error during video collection: {error_message}")
    finally:
        # Clean up the local output file
        if os.path.exists(output_path):
            os.remove(output_path)
        await active_jobs.set_status(job_id, "completed")
        await active_jobs.delete_job(job_id)

        @app.get("/health")
        async def health_check():
            """
            Health check endpoint to verify the API is running.
            """
            return JSONResponse({"status": "ok", "message": "Service is healthy."})


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
    await active_jobs.set_job(job_id, {"status": "started", "youtube_url": youtube_url, "start_time": datetime.now().isoformat()})
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
    await active_jobs.set_job(job_id, {"status": "started", "youtube_url": youtube_url, "start_time": datetime.now().isoformat()})
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


@app.websocket("/ws/latest")
async def websocket_latest_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for clients to listen for updates about the latest video.
    """
    await latest_video_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep connection alive
    except WebSocketDisconnect:
        latest_video_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
