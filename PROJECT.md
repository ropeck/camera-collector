# Camera Collector

An automated system that captures frames from live YouTube streams (specifically beach webcam feeds), generates time-lapse videos, creates visual collages, and produces monthly video compilations. The system runs on Kubernetes with Google Cloud Storage integration.

## Overview

This project captures daily sunrise and sunset videos from the Seacliff Beach webcam feed. Key capabilities:

- Automated video capture based on astronomical sunrise/sunset times
- Real-time job monitoring via WebSocket connections
- Grid collage generation from multiple videos
- Monthly compilation video creation
- REST API for all operations
- Web gallery for browsing content

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User Browser                                 │
│                    (Gallery SPA / API Client)                        │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │ HTTP/REST      │ WebSocket │
                    ▼                ▼           │
┌─────────────────────────────────────────────────────────────────────┐
│                     FastAPI Application                              │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Uvicorn ASGI Server                        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│         │              │              │              │               │
│         ▼              ▼              ▼              ▼               │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐        │
│  │  app.py   │  │ collage.py│  │ concat.py │  │  sun.py   │        │
│  │  (API)    │  │ (Images)  │  │ (Videos)  │  │(Scheduler)│        │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘        │
│         │              │              │                              │
│         └──────────────┼──────────────┘                              │
│                        ▼                                             │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              FFmpeg / yt-dlp Processing                       │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  YouTube Live   │    │  Google Cloud   │    │   Linux cron    │
│     Stream      │    │    Storage      │    │   (sun.py)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Components

### Main Application (app.py)

The FastAPI application handles HTTP requests, WebSocket connections, and orchestrates video processing.

**Key Classes:**

| Class | Purpose |
|-------|---------|
| `ConnectionManager` | Manages job-specific WebSocket connections |
| `LatestVideoConnectionManager` | Broadcasts latest video updates to all clients |
| `ThreadSafeJobs` | Thread-safe dictionary for tracking active jobs |

**Key Functions:**

| Function | Purpose |
|----------|---------|
| `run_subprocess_blocking()` | Pipes yt-dlp → FFmpeg for 15-second video capture |
| `collect_and_upload_video()` | Async orchestration of video collection pipeline |
| `upload_to_gcs()` | Upload video to GCS with timestamp-based naming |

### Collage Module (collage.py)

Generates grid collages from multiple videos.

**Features:**
- Filter videos by date and time of day (sunrise/sunset)
- Extract frames at configurable timestamps
- Create grid layouts (default 5x6)
- Upload collages to GCS

### Concatenation Module (concat.py)

Creates monthly compilation videos.

**Features:**
- List and filter videos by month
- Concatenate without re-encoding (copy codec)
- Cache generated compilations
- Extract metadata (duration, file size)

### Scheduling Module (sun.py)

Calculates sunrise/sunset times and schedules collection jobs.

**Location:** Seacliff, CA (36.9741°N, 121.9158°W)

**Daily Schedule:**
1. Sunrise time
2. 15 minutes before sunset
3. Sunset time

Uses Linux `at` command for one-time scheduled execution. Runs via cron at 5 AM daily.

## API Endpoints

### Health & Status

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Root with version info and available endpoints |
| `/health` | GET | Health check |

### Video Collection

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/collection/start` | POST | Start collection with default YouTube URL |
| `/collection/start/{youtube_url}` | POST | Start collection with custom URL |
| `/collection/status/{job_id}` | GET | Get status of specific job |
| `/active-collections` | GET | List all active collection jobs |

### Collage Generation

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/collage/generate` | POST | Generate grid collage with filters |

**Parameters:**
- `year`, `month` - Filter by date
- `time_filter` - "sunrise" or "sunset"
- `grid_cols`, `grid_rows` - Grid dimensions (default 5x6)
- `frame_time` - Seconds into video to extract (default 7.0)

### Monthly Compilations

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/months` | GET | List all months with video counts |
| `/api/compilation/generate` | POST | Generate or retrieve monthly compilation |
| `/api/compilation/{year}/{month}` | GET | Check compilation status |

### WebSocket Endpoints

| Endpoint | Description |
|----------|-------------|
| `/ws/{job_id}` | Job-specific real-time updates |
| `/ws/latest` | Broadcast channel for latest video notifications |

### Frontend

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/gallery` | GET | Gallery single-page application |
| `/static/*` | GET | Static assets (CSS, JavaScript) |

## Video Collection Pipeline

```
1. POST /collection/start or sun.py schedules via cron
                    │
                    ▼
2. Create job_id (UUID) and async task
                    │
                    ▼
3. yt-dlp fetches stream → pipes to FFmpeg
                    │
                    ▼
4. FFmpeg captures 15-second clip (h264 + AAC)
                    │
                    ▼
5. Upload to GCS: BUCKET/YYYY/MM/seacliff-{timestamp}.mp4
                    │
                    ▼
6. WebSocket clients notified of completion
                    │
                    ▼
7. Temp files cleaned up
```

## Technology Stack

| Category | Technology |
|----------|------------|
| Language | Python 3.13 |
| Framework | FastAPI with Uvicorn |
| Video Capture | yt-dlp |
| Video Processing | FFmpeg |
| Image Processing | Pillow |
| Cloud Storage | Google Cloud Storage |
| Real-time | WebSockets |
| Container | Docker |
| Orchestration | Kubernetes |
| CI/CD | GitHub Actions |

**Python Dependencies:**
- fastapi, uvicorn
- google-cloud-storage
- yt-dlp
- pillow
- astral, pytz
- aiofiles
- pytest, pytest-asyncio, httpx

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BUCKET_NAME` | `fogcat-webcam` | GCS bucket name |
| `SERVICE_ACCOUNT_FILE` | `/app/service-account-key.json` | GCS credentials path |
| `DEFAULT_YOUTUBE_URL` | (Seacliff webcam) | Default stream URL |
| `BUILD_TIME` | (optional) | Docker build timestamp |
| `TZ` | `America/Los_Angeles` | Timezone |

### GCS Bucket Structure

```
fogcat-webcam/
├── YYYY/MM/
│   ├── seacliff-YYYY-MM-DDTHH:MM-SS±ZZZZ.mp4   (daily videos)
│   ├── collages/
│   │   └── collage-YYYY-MM-sunrise-5x6.jpg
│   └── compilations/
│       ├── sunrise-YYYY-MM.mp4
│       ├── sunset-YYYY-MM.mp4
│       └── all-YYYY-MM.mp4
```

## Deployment

### Kubernetes Resources

**Deployment (k8s/deployment.yaml):**
- 1 replica
- Resource limits: 1GB memory / 500m CPU
- Resource requests: 256MB memory / 250m CPU
- GCP credentials mounted from secret

**Service (k8s/service.yaml):**
- ClusterIP type
- Port 80 → container port 5000

### Container Startup (endpoint.sh)

1. Set timezone to America/Los_Angeles
2. Start daemon services (atd, syslog, cron)
3. Execute sun.py to schedule today's collections
4. Configure Google Cloud credentials
5. Start FastAPI application
6. Tail logs

### CI/CD Pipeline

Triggered on push to `main` branch:

1. Build Docker image with Buildx
2. Push to Docker Hub with `latest` and SHA tags
3. Authenticate to GKE
4. Deploy to Kubernetes cluster
5. Verify rollout status

## Development

### Local Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run development server
python app.py
```

The server runs on `http://localhost:5000`.

### Running Tests

```bash
pytest -v
```

72+ tests covering all modules with pytest-asyncio for async endpoints.

### Docker Commands

```bash
# Build image
make docker

# Run container
make run

# Interactive shell
make shell
```

## File Reference

| File | Description |
|------|-------------|
| `app.py` | Main FastAPI application with all endpoints |
| `collage.py` | Grid collage generation from videos |
| `concat.py` | Video concatenation and monthly compilation |
| `sun.py` | Sunrise/sunset scheduling |
| `start_collection.py` | Client script for initiating collections |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container image definition |
| `endpoint.sh` | Container startup script |
| `k8s/deployment.yaml` | Kubernetes Deployment |
| `k8s/service.yaml` | Kubernetes Service |
| `static/` | Gallery SPA (HTML, CSS, JavaScript) |

## Related Projects

- **collector-webapp**: Flask application that displays videos collected by this system
