import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
import uuid
import logging
import os
from datetime import datetime
from collections import defaultdict

app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

# Retrieve build time or set server start time
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

# Track active job UUIDs
active_jobs = defaultdict(str)

def get_active_jobs():
    return active_jobs

# Async subprocess function
async def run_async_subprocess(job_id: str):
    """
    Run a subprocess asynchronously and send updates via WebSocket.
    """
    process = None
    try:
        # Add the job ID to the active jobs dictionary
        active_jobs[job_id] = "running"
        logging.info(f"Job {job_id} started.")

        command = ["./gcloud_upload.sh"]
        logging.info(f"Running command: {' '.join(command)} job ID: {job_id}")

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Notify that the job has started
        await manager.send_message(job_id, f"Job {job_id} started.")

        # Read stdout and send updates
        while True:
            line = await process.stdout.readline()
            if line:
                message = line.decode().strip()
                await manager.send_message(job_id, f"Output: {message}")
                logging.info(f"Job {job_id} output: {message}")
            elif process.returncode is not None:  # Process has finished
                break

        # Wait for the process to finish
        stdout, stderr = await process.communicate()


        # Notify on completion or error
        if process.returncode == 0:
            await manager.send_message(job_id, f"Job {job_id} completed successfully.")
            active_jobs[job_id] = "completed"
            logging.info(f"Job {job_id} completed successfully.")
        else:
            error_message = stderr.decode().strip()
            await manager.send_message(job_id, f"Job {job_id} failed with error: {error_message}")
            active_jobs[job_id] = "failed"
            logging.error(f"Job {job_id} failed with error: {error_message}")
    except Exception as e:
        error_message = str(e)
        await manager.send_message(job_id, f"Error with Job ID {job_id}: {error_message}")
        active_jobs[job_id] = "error"
        logging.error(f"Error with Job ID {job_id}: {error_message}")
    finally:
        # Ensure process resources are cleaned up
        if process and process.returncode is None:
            process.kill()
            await process.wait()
            logging.info(f"Process for Job {job_id} was forcefully terminated.")

        # Safeguard against unintended deletions
        current_status = active_jobs.get(job_id)
        if current_status in ["running", "error"]:
            del active_jobs[job_id]


@app.get("/")
async def root():
    """
    Root endpoint that returns API status and version information.
    """
    version_info = ("BUILD_TIME: " + BUILD_TIME) if BUILD_TIME else ("SERVER_START_TIME: " + SERVER_START_TIME)
    return JSONResponse({"message": "Camera Collector API is running!", "version": version_info})


@app.post("/collection/start")
async def start_collection():
    """
    Start a collection job and run asynchronously.
    """
    # Generate a unique job ID
    job_id = str(uuid.uuid4())

    # Schedule the subprocess task
    asyncio.create_task(run_async_subprocess(job_id))

    logging.info(f"Collection started with Job ID: {job_id}")

    # Return the job ID to the client
    return JSONResponse({"job_id": job_id, "message": f"Collection started with Job ID {job_id}"})


@app.get("/collection/status/{job_id}")
async def collection_status(job_id: str):
    """
    Retrieve the status of a specific job ID.
    """
    if job_id in active_jobs:
        status = active_jobs[job_id]
        logging.info(f"Status for Job ID {job_id}: {status}")
        return JSONResponse({"job_id": job_id, "status": status})
    else:
        logging.warning(f"Job ID {job_id} not found.")
        raise HTTPException(status_code=404, detail="Job ID not found.")


@app.get("/active-collections")
async def get_active_collections():
    """
    Retrieve the list of currently active collection job IDs.
    """
    logging.info("Fetching active collections.")
    return JSONResponse({"active_jobs": list(active_jobs)})


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


# Run the app on port 5000 when executed directly
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)
