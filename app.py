from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import JSONResponse
import asyncio
import subprocess
import uuid

app = FastAPI()

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]

    async def send_message(self, client_id: str, message: str):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_text(message)


manager = ConnectionManager()

# Store active collection jobs
active_jobs = set()

# Background task to process video collection
async def collect_stream(job_id: str, manager: ConnectionManager):
    try:
        # Add job to active_jobs
        active_jobs.add(job_id)
        # Notify WebSocket client that collection has started
        await manager.send_message(job_id, f"Collection started with Job ID: {job_id}")

        # Simulated long-running task (e.g., replacing with an ffmpeg command)
        for i in range(1, 6):  # Simulate 5 steps of progress
            await asyncio.sleep(10)  # Replace with actual work like frame processing
            await manager.send_message(job_id, f"Progress: Step {i}/5")

        # Notify WebSocket client that collection has completed
        await manager.send_message(job_id, f"Collection completed for Job ID: {job_id}")
    except Exception as e:
        await manager.send_message(job_id, f"Error with Job ID {job_id}: {str(e)}")
    finally:
        # Remove job from active_jobs
        active_jobs.discard(job_id)


@app.get("/")
async def root():
    return JSONResponse({"message": "Camera Collector API is running!"})


@app.post("/collect")
async def collect_stream_endpoint(background_tasks: BackgroundTasks):
    """
    Start a new collection job. Returns a unique job ID.
    """
    # Generate a unique job ID
    job_id = str(uuid.uuid4())

    # Add the collection task to the background
    background_tasks.add_task(collect_stream, job_id, manager)

    # Return the job ID to the client
    return JSONResponse({"job_id": job_id, "message": f"Collection started with Job ID {job_id}"})


@app.get("/active-collections")
async def get_active_collections():
    """
    Retrieve the list of currently active collection job IDs.
    """
    return JSONResponse({"active_jobs": list(active_jobs)})


@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """
    WebSocket connection for real-time notifications for a specific job.
    """
    await manager.connect(websocket, job_id)
    try:
        while True:
            # Keep the connection alive by waiting for messages (if needed).
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(job_id)
        print(f"WebSocket connection closed for Job ID: {job_id}")


# Run the app on port 5000 when executed directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
