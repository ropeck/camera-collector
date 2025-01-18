from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit
import threading
import time

app = Flask(__name__)
socketio = SocketIO(app)  # Initialize Flask-SocketIO with the app

# Simulated in-memory job store
jobs = {}

def youtube_collection(job_id):
    """Simulate a long-running YouTube collection task."""
    time.sleep(20)  # Simulate collection time
    jobs[job_id] = {"status": "completed", "video_url": f"/videos/{job_id}.mp4"}

    # Notify the client via WebSocket
    socketio.emit('job_update', {'job_id': job_id, 'status': 'completed', 'video_url': f"/videos/{job_id}.mp4"})

@app.route('/start_collection', methods=['POST'])
def start_collection():
    """Start the YouTube collection process."""
    job_id = request.form.get("job_id")  # Generate or receive a unique job ID
    jobs[job_id] = {"status": "in_progress"}  # Mark the job as in progress

    # Start the collection in a background thread
    thread = threading.Thread(target=youtube_collection, args=(job_id,))
    thread.start()

    return jsonify({"job_id": job_id, "status": "started"})

@app.route('/job_status/<job_id>', methods=['GET'])
def job_status(job_id):
    """Check the status of the job."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)

@app.route('/')
def index():
    """Serve the main HTML page."""
    return render_template('index.html')

if __name__ == '__main__':
    socketio.run(app, debug=True)
