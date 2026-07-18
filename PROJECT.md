# Camera Collector

An automated system that captures frames from live YouTube streams (specifically beach webcam feeds), generates time-lapse videos, creates visual collages, and produces monthly video compilations. Google Cloud Storage backs everything.

> **Deployment (as of 2026-07-18):** split across Cloud Run (this app's API/gallery)
> and a NAS (the actual VPN-dependent capture). GKE is retired. See "Deployment"
> below — the Kubernetes sections further down describe the old, now-inactive setup.

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

**Split architecture** (as of 2026-07-18): the FastAPI app (API, gallery, WebSocket)
runs on **Cloud Run**; the actual video capture (which needs the Surfshark VPN to
avoid YouTube bot detection) runs on a **NAS** (`pi@nas.lan`) via systemd timers.
GKE is scaled to 0 and no longer live — see "Kubernetes Resources (retired)" below.

### Cloud Run (app.py — API, gallery, compilation, collage)

```bash
gcloud builds submit . --project=k8s-project-441922 \
  --tag us-central1-docker.pkg.dev/k8s-project-441922/cloud-run-source-deploy/camera-collector:TAG

gcloud run deploy camera-collector --project=k8s-project-441922 --region=us-west1 \
  --image=us-central1-docker.pkg.dev/k8s-project-441922/cloud-run-source-deploy/camera-collector:TAG \
  --command=python3 --args=app.py \
  --service-account=weather@k8s-project-441922.iam.gserviceaccount.com \
  --set-env-vars="BUCKET_NAME=fogcat-webcam,SERVICE_ACCOUNT_FILE=/secrets/service-account-key.json" \
  --set-secrets="/secrets/service-account-key.json=home-app-gcp-key:latest"
```

Traffic reaches Cloud Run via the shared `fogcat5-urlmap` load balancer (project
`k8s-project-441922`, one LB covers every `*.fogcat5.com` app). Two backend
services point at this same Cloud Run service, split by path:

- `/` and `/collection/*` (the actual capture trigger) → `bes-camera-collector`,
  **IAP-gated**
- `/api/*`, `/collage/generate`, `/gallery`, `/static/*` → `bes-camera-collector-open`,
  **public** — the Netlify video-archive viewer
  (`legendary-figolla-368e7a.netlify.app`) fetches these directly from the browser
  and can't do an interactive Google login

Cloud Run's own IAM (`run.invoker`) is service-wide, not path-scoped, so making the
open backend service work at all requires `allUsers` on the whole Cloud Run
service — which would otherwise let anyone bypass IAP entirely by hitting
`/collection/start` on the raw `*.run.app` URL directly. `_require_iap()` in
`app.py` closes that gap: it checks for IAP's own `X-Goog-Authenticated-User-Email`
header (which only IAP can set — not spoofable by a direct caller) before starting
a capture, regardless of which URL was used to reach it.

Deploying a new image via `gcloud run deploy` has been observed to reset the
`run.invoker` IAM policy — re-grant both bindings after any redeploy:
```bash
gcloud run services add-iam-policy-binding camera-collector --project=k8s-project-441922 --region=us-west1 \
  --member="serviceAccount:service-289658173247@gcp-sa-iap.iam.gserviceaccount.com" --role="roles/run.invoker"
gcloud run services add-iam-policy-binding camera-collector --project=k8s-project-441922 --region=us-west1 \
  --member="allUsers" --role="roles/run.invoker"
```

### NAS (capture.py, sun.py — the actual yt-dlp/ffmpeg capture)

Runs on `pi@nas.lan` at `/home/pi/camera-collector/` — **not** this repo's code
directly. `capture.py` there is a standalone extraction of
`run_subprocess_blocking()`/`upload_to_gcs()` from this `app.py` (no
FastAPI/WebSocket needed for a one-shot capture), and `sun.py` is the same
astral-based scheduling logic in this repo, adapted to trigger the local script
via `at` instead of POSTing to the (now IAP-gated) public API. Modeled on the
sibling `frame-fetcher` setup on the same NAS — same Surfshark VPN, same
`/var/lock/surfshark-vpn.lock` mutex (both scripts share one WireGuard identity
and must not run concurrently, or the VPN provider misroutes return traffic
between them).

- Daily scheduler: `camera-collector-sun.timer` (systemd, 5am — mirrors the old
  `0 5 * * * /app/sun.py` crontab below)
- VPN: reuses the same `surfshark-wg0-conf` Secret Manager secret, brought up via
  real kernel `wg-quick` (not a k8s sidecar) — this is what makes it work at all.
  A userspace WireGuard-in-Cloud-Run attempt (`wireproxy`) completed the
  handshake but couldn't pass data through Cloud Run's sandboxed network stack.
- GCS upload timeout bumped to 600s (`upload_from_filename(..., timeout=600)`) —
  the VPN tunnel's throughput for a full video (~2.5 min upload) exceeds the
  client library's 120s default.

### Kubernetes Resources (retired)

**Deployment (k8s/deployment.yaml):**
- 1 replica, strategy: Recreate (single e2-medium node)
- Resource limits: 1GB memory / 500m CPU
- Resource requests: 256MB memory / 100m CPU
- GCP credentials mounted from `gcp-credentials` k8s secret
- Cluster: `my-first-cluster`, zone `us-west1-a`, project `k8s-project-441922`

**Pod containers:**
- `camera-collector` — FastAPI app, video capture, scheduling
- `wireguard` — Surfshark VPN sidecar (linuxserver/wireguard image)
- `route-manager` — sets up iptables NAT through wg0

**Init containers (run at pod start, in order):**
1. `init-sysctl` — enables ip_forward on the node
2. `fetch-vpn-config` — fetches WireGuard config from GCP Secret Manager
   (`surfshark-wg0-conf`, project `k8s-project-441922`) and writes to shared
   `emptyDir` volume at `/config/wg_confs/wg0.conf`

**WireGuard key rotation:**
1. Delete old key from Surfshark portal (my.surfshark.com → VPN → Manual Setup → WireGuard)
2. Create new key (name it `YYYYMMDD-vpn`)
3. Update GCP secret:
   ```bash
   CLOUDSDK_ACTIVE_CONFIG_NAME=fogcat5 gcloud secrets versions add surfshark-wg0-conf \
       --project=k8s-project-441922 --data-file=<new_conf>
   ```
4. Restart pod to pick up new config:
   ```bash
   kubectl rollout restart deployment/camera-collector
   ```

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

Note: yt-dlp downloads go through the Surfshark VPN (Netherlands exit node) to
avoid YouTube bot detection. The VPN is managed by the wireguard sidecar; the
camera-collector container routes its traffic through it automatically.

### CI/CD Pipeline

The GitHub Actions push-to-GKE pipeline described here is retired along with the
GKE deployment above. Cloud Run deploys are currently manual (`gcloud builds
submit` + `gcloud run deploy`, see "Cloud Run" above) — no CI/CD wired up yet for
the new path. The NAS side (`capture.py`/`sun.py`) is deployed by hand via `scp`,
not from this repo's CI at all.

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
