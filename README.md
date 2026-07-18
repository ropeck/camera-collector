# Camera Collector

Captures daily sunrise and sunset clips from the Seacliff Beach webcam (YouTube live stream),
stores them in GCS, and serves a web gallery with monthly browsing and compilation generation.

> **Deployment (as of 2026-07-18):** split across Cloud Run (this app's API/gallery)
> and a NAS (the actual VPN-dependent capture, still via Surfshark WireGuard, now
> real kernel `wg-quick` instead of a k8s sidecar). GKE is retired. See
> [PROJECT.md](PROJECT.md#deployment) for the full picture — the GKE/Kubernetes
> sections in this README describe the old, now-inactive setup.

Live: [weather.fogcat5.com](https://weather.fogcat5.com) (gallery/API), capture on `pi@nas.lan`

## Features

- **Automated capture**: Scheduled around astronomical sunrise/sunset via `sun.py` + `at`
- **VPN routing**: All yt-dlp traffic exits through Surfshark NL (bot detection bypass)
- **Web gallery**: Browse clips by month, trigger compilations via REST API
- **GCS storage**: Videos and thumbnails stored in `fogcat-webcam` bucket
- **WebSocket updates**: Real-time job status during active collections
- **CI/CD**: Push to `main` → Docker Hub build → GKE deploy (GitHub Actions)

## Project Structure

```
camera-collector/
├── app.py                  # FastAPI app — REST API + WebSocket
├── sun.py                  # Sunrise/sunset scheduler (astral)
├── start_collection.py     # yt-dlp wrapper, called by cron/at
├── collage.py              # Grid collage generation
├── concat.py               # Video compilation (ffmpeg)
├── endpoint.sh             # Container entrypoint
├── Dockerfile
├── requirements.txt
└── k8s/
    ├── deployment.yaml     # 3-container pod: app + wireguard + route-manager
    └── service.yaml
```

See [PROJECT.md](PROJECT.md) for full architecture docs.

## Deployment

See [PROJECT.md](PROJECT.md#deployment) for the current split setup: the
FastAPI app on Cloud Run (IAP-gated, with an open path for the public video
archive viewer), capture on a NAS via systemd timers. The `kubectl apply -f
k8s/` GKE flow below is retired (scaled to 0, not deleted).

```bash
# Get GKE credentials
CLOUDSDK_ACTIVE_CONFIG_NAME=fogcat5 \
  gcloud container clusters get-credentials my-first-cluster \
  --zone=us-west1-a --project=k8s-project-441922

# Deploy
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

The deployment pulls WireGuard config from GCP Secret Manager (`surfshark-wg0-conf`)
at pod start — no PVC, no stale keys. To rotate the VPN key see CHANGELOG.md.

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py   # runs on http://localhost:5000
```
