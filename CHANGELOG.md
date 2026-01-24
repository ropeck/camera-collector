# Changelog

All notable changes to the Camera Collector project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Planned
- Sunset/sunrise collage image generation
- Video compositing features
- Concatenate videos into longer compilations

## [0.5.0] - 2026-01-24

### Added
- Comprehensive test suite with 72 tests covering all components
- Tests for FastAPI endpoints, WebSocket managers, and video pipeline
- Tests for sunrise/sunset scheduling logic (sun.py)
- Tests for collection client (start_collection.py)
- pytest-asyncio support for async testing
- pytest.ini configuration

### Changed
- Refactored sun.py to wrap main logic in `schedule_collections()` for testability

## [0.4.0] - 2025-03-18

### Added
- Google DNS configuration for improved network reliability
- Network information display on startup
- External IP logging for debugging

### Changed
- Removed cookie-based authentication for yt-dlp
- Let yt-dlp choose the best format automatically

## [0.3.0] - 2025-01-28

### Added
- WebSocket updates when new videos are collected (CC-22)
- Real-time job status notifications via WebSocket
- Collection client logging improvements
- Metadata for overlay images
- Health check endpoint

### Changed
- Improved WebSocket messaging with more detailed status updates
- Fetch overlay video after scheduled collection to prime cache

## [0.2.0] - 2025-01-26

### Added
- FFmpeg subprocess handling for 15-second video capture (CC-19)
- Async video pipeline with proper threading
- Custom filename format with timestamps
- API documentation

### Fixed
- Threading issues with API server
- Syntax errors in subprocess handling

## [0.1.0] - 2025-01-03

### Added
- GitHub Actions CI/CD pipeline for Docker builds
- Automated deployment to GKE cluster
- Code cleanup and refactoring

### Changed
- Improved code structure based on AI-assisted review

## [0.0.2] - 2024-12-07

### Added
- Path configuration for `at` and `atq` commands
- GCP SDK path setup (gcloud, gsutil)
- Syslog daemon for logging
- Cron log file tailing

### Fixed
- Timezone configuration in cron jobs

## [0.0.1] - 2024-11-29

### Added
- Initial project setup
- Docker container configuration
- Kubernetes deployment manifests
- Basic video collection from YouTube live streams
- Google Cloud Storage upload functionality
- Sunrise/sunset scheduling using astral library
- FastAPI web service
- Pacific timezone support

[Unreleased]: https://github.com/ropeck/camera-collector/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/ropeck/camera-collector/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/ropeck/camera-collector/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/ropeck/camera-collector/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ropeck/camera-collector/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ropeck/camera-collector/compare/v0.0.2...v0.1.0
[0.0.2]: https://github.com/ropeck/camera-collector/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/ropeck/camera-collector/releases/tag/v0.0.1
