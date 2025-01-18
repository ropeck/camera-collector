import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import uuid

app = FastAPI()

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, job_id: str):
        await websocket.accept()
        self.active_connections[job_id] = websocket

    def disconnect(self, job_id: str):
        if job_id in self.active_connections:
            del self.active_connections[job_id]

    async def send_message(self, job_id: str, message: str):
        if job_id in self.active_connections:
            await self.active_connections[job_id].send_text(message)


manager = ConnectionManager()


# Async subprocess function
async def run_async_subprocess(job_id: str):
    """
    Run a subprocess asynchronously and send updates via WebSocket.
    """
    command = ["./gcloud_upload.sh"]
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    # Notify that the job has started
    await manager.send_message(job_id, f"Job {job_id} started.")

    # Read stdout and stderr asynchronously
    while True:
        line = await process.stdout.readline()
        if line:
            await manager.send_message(job_id, f"Output: {line.decode().strip()}")
        elif process.returncode is not None:  # Process has finished
            break

    # Wait for the process to finish
    stdout, stderr = await process.communicate()

    # Notify on completion or error
    if process.returncode == 0:
        await manager.send_message(job_id, f"Job {job_id} completed successfully.")
    else:
        await manager.send_message(job_id, f"Job {job_id} failed with error: {stderr.decode().strip()}")


@app.get("/")
async def root():
    return JSONResponse({"message": "Camera Collector API is running!"})


@app.post("/collect")
async def collect_stream():
    """
    Start a collection job and run asynchronously.
    """
    # Generate a unique job ID
    job_id = str(uuid.uuid4())

    # Schedule the subprocess task
    asyncio.create_task(run_async_subprocess(job_id))

    # Return the job ID to the client
    return JSONResponse({"job_id": job_id, "message": f"Collection started with Job ID {job_id}"})


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
        print(f"WebSocket connection closed for Job ID: {job_id}")


# Run the app on port 5000 when executed directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
