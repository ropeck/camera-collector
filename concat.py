"""
Video concatenation module for camera-collector.

This module provides functionality to concatenate daily sunrise/sunset videos
into monthly compilation videos stored in Google Cloud Storage.
"""

import logging
import os
import subprocess
import tempfile
from datetime import datetime
from typing import Optional

from google.cloud import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

# Approximate times for filtering sunrise vs sunset (in 24h format)
SUNRISE_HOUR_RANGE = (5, 10)  # 5 AM to 10 AM
SUNSET_HOUR_RANGE = (16, 21)  # 4 PM to 9 PM


def extract_hour_from_filename(filename: str) -> Optional[int]:
    """
    Extract the hour from a video filename.

    Expected format: seacliff-YYYY-MM-DDTHH:MM-SS+ZZZZ.mp4

    Args:
        filename: The video filename

    Returns:
        Hour as integer, or None if parsing fails
    """
    try:
        basename = os.path.basename(filename)
        timestamp_part = basename.replace("seacliff-", "").replace(".mp4", "")
        hour_str = timestamp_part.split("T")[1].split(":")[0]
        return int(hour_str)
    except (IndexError, ValueError):
        return None


def list_videos_for_month(
    storage_client: storage.Client,
    bucket_name: str,
    year: int,
    month: int,
    time_filter: Optional[str] = None,
) -> list[str]:
    """
    List video blobs from GCS for a specific month.

    Args:
        storage_client: GCS client instance
        bucket_name: Name of the GCS bucket
        year: Year to filter by
        month: Month to filter by
        time_filter: "sunrise", "sunset", or None for all videos

    Returns:
        List of blob names matching the filters, sorted chronologically
    """
    prefix = f"{year}/{month:02d}/"
    bucket = storage_client.bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=prefix)

    video_blobs = []
    for blob in blobs:
        # Skip non-video files and files in subdirectories (collages, compilations)
        if not blob.name.endswith(".mp4"):
            continue
        if "/collages/" in blob.name or "/compilations/" in blob.name:
            continue

        # Apply time filter if specified
        if time_filter:
            hour = extract_hour_from_filename(blob.name)
            if hour is not None:
                if time_filter == "sunrise" and not (SUNRISE_HOUR_RANGE[0] <= hour <= SUNRISE_HOUR_RANGE[1]):
                    continue
                elif time_filter == "sunset" and not (SUNSET_HOUR_RANGE[0] <= hour <= SUNSET_HOUR_RANGE[1]):
                    continue

        video_blobs.append(blob.name)

    # Sort by filename (which contains timestamp) for chronological order
    video_blobs.sort()
    return video_blobs


def get_video_counts_for_month(
    storage_client: storage.Client,
    bucket_name: str,
    year: int,
    month: int,
) -> dict:
    """
    Get counts of sunrise and sunset videos for a month.

    Args:
        storage_client: GCS client instance
        bucket_name: Name of the GCS bucket
        year: Year to count
        month: Month to count

    Returns:
        Dictionary with sunrise_count, sunset_count, and total_count
    """
    sunrise_videos = list_videos_for_month(storage_client, bucket_name, year, month, "sunrise")
    sunset_videos = list_videos_for_month(storage_client, bucket_name, year, month, "sunset")
    all_videos = list_videos_for_month(storage_client, bucket_name, year, month, None)

    return {
        "sunrise_count": len(sunrise_videos),
        "sunset_count": len(sunset_videos),
        "total_count": len(all_videos),
    }


def get_compilation_blob_name(year: int, month: int, time_filter: Optional[str]) -> str:
    """
    Generate the blob name for a compilation video.

    Args:
        year: Year of the compilation
        month: Month of the compilation
        time_filter: "sunrise", "sunset", or None for all

    Returns:
        Blob name for the compilation
    """
    filter_name = time_filter if time_filter else "all"
    return f"{year}/{month:02d}/compilations/{filter_name}-{year}-{month:02d}.mp4"


def check_compilation_exists(
    storage_client: storage.Client,
    bucket_name: str,
    blob_name: str,
) -> dict:
    """
    Check if a compilation video already exists in GCS.

    Args:
        storage_client: GCS client instance
        bucket_name: Name of the GCS bucket
        blob_name: Name of the compilation blob

    Returns:
        Dictionary with exists, url, size_bytes, and updated fields
    """
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    if blob.exists():
        blob.reload()
        return {
            "exists": True,
            "url": f"https://storage.googleapis.com/{bucket_name}/{blob_name}",
            "size_bytes": blob.size,
            "updated": blob.updated.isoformat() if blob.updated else None,
        }

    return {"exists": False}


def download_video_from_gcs(
    storage_client: storage.Client,
    bucket_name: str,
    blob_name: str,
    local_path: str,
) -> None:
    """
    Download a video from GCS to a local path.

    Args:
        storage_client: GCS client instance
        bucket_name: Name of the GCS bucket
        blob_name: Name of the blob to download
        local_path: Local path to save the video
    """
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.download_to_filename(local_path)
    logging.info(f"Downloaded {blob_name} to {local_path}")


def concatenate_videos(video_paths: list[str], output_path: str) -> None:
    """
    Concatenate multiple videos using ffmpeg concat demuxer (no re-encoding).

    Args:
        video_paths: List of local video file paths to concatenate
        output_path: Path for the output concatenated video
    """
    if not video_paths:
        raise ValueError("No video paths provided for concatenation")

    # Create concat file list
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        concat_file = f.name
        for path in video_paths:
            # Use absolute paths and escape single quotes
            abs_path = os.path.abspath(path)
            f.write(f"file '{abs_path}'\n")

    try:
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",  # No re-encoding
            "-movflags", "+faststart",  # Web streaming optimization
            output_path,
        ]
        logging.info(f"Concatenating {len(video_paths)} videos: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=600,  # 10 minute timeout
        )

        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed: {result.stderr.decode()}")

        logging.info(f"Created compilation: {output_path}")
    finally:
        if os.path.exists(concat_file):
            os.remove(concat_file)


def upload_compilation_to_gcs(
    storage_client: storage.Client,
    bucket_name: str,
    local_path: str,
    blob_name: str,
) -> str:
    """
    Upload a compilation video to GCS.

    Args:
        storage_client: GCS client instance
        bucket_name: Name of the GCS bucket
        local_path: Local path of the video to upload
        blob_name: Name for the blob in GCS

    Returns:
        Public URL of the uploaded compilation
    """
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(local_path, content_type="video/mp4")

    logging.info(f"Uploaded compilation to {blob_name}")
    return f"https://storage.googleapis.com/{bucket_name}/{blob_name}"


def extract_thumbnail(video_path: str, output_path: str, time_offset: float = None) -> bool:
    """
    Extract a thumbnail frame from a video using ffmpeg.

    Args:
        video_path: Path to the video file
        output_path: Path for the output thumbnail image
        time_offset: Time in seconds to extract frame (default: 50% of duration)

    Returns:
        True if successful, False otherwise
    """
    # If no time_offset specified, get duration and use 50%
    if time_offset is None:
        duration = get_video_duration(video_path)
        time_offset = duration * 0.5 if duration > 0 else 5.0

    cmd = [
        "ffmpeg",
        "-y",  # Overwrite output
        "-ss", str(time_offset),  # Seek to time
        "-i", video_path,
        "-vframes", "1",  # Extract 1 frame
        "-q:v", "2",  # High quality JPEG
        output_path,
    ]

    logging.info(f"Extracting thumbnail at {time_offset}s: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode != 0:
            logging.warning(f"Failed to extract thumbnail: {result.stderr.decode()}")
            return False
        logging.info(f"Created thumbnail: {output_path}")
        return True
    except subprocess.TimeoutExpired:
        logging.warning("Thumbnail extraction timed out")
        return False


def get_thumbnail_blob_name(year: int, month: int, time_filter: Optional[str]) -> str:
    """
    Generate the blob name for a compilation thumbnail.

    Args:
        year: Year of the compilation
        month: Month of the compilation
        time_filter: "sunrise", "sunset", or None for all

    Returns:
        Blob name for the thumbnail
    """
    filter_name = time_filter if time_filter else "all"
    return f"{year}/{month:02d}/compilations/{filter_name}-{year}-{month:02d}-thumb.jpg"


def upload_thumbnail_to_gcs(
    storage_client: storage.Client,
    bucket_name: str,
    local_path: str,
    blob_name: str,
) -> str:
    """
    Upload a thumbnail image to GCS.

    Args:
        storage_client: GCS client instance
        bucket_name: Name of the GCS bucket
        local_path: Local path of the thumbnail to upload
        blob_name: Name for the blob in GCS

    Returns:
        Public URL of the uploaded thumbnail
    """
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(local_path, content_type="image/jpeg")

    logging.info(f"Uploaded thumbnail to {blob_name}")
    return f"https://storage.googleapis.com/{bucket_name}/{blob_name}"


def get_video_duration(video_path: str) -> float:
    """
    Get the duration of a video in seconds using ffprobe.

    Args:
        video_path: Path to the video file

    Returns:
        Duration in seconds
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]

    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode != 0:
        logging.warning(f"Could not get duration for {video_path}")
        return 0.0

    try:
        return float(result.stdout.decode().strip())
    except ValueError:
        return 0.0


def generate_compilation(
    storage_client: storage.Client,
    bucket_name: str,
    year: int,
    month: int,
    time_filter: Optional[str] = None,
    force_regenerate: bool = False,
) -> dict:
    """
    Generate a monthly compilation video from daily videos.

    This function orchestrates the full workflow:
    1. Check if compilation already exists (return cached if so)
    2. List videos for the month
    3. Download videos to temp directory
    4. Concatenate using ffmpeg
    5. Upload to GCS
    6. Clean up temp files

    Args:
        storage_client: GCS client instance
        bucket_name: Name of the GCS bucket
        year: Year of videos to compile
        month: Month of videos to compile
        time_filter: "sunrise", "sunset", or None for all videos
        force_regenerate: If True, regenerate even if cached version exists

    Returns:
        Dictionary with url, video_count, duration_seconds, cached, and generated_at
    """
    blob_name = get_compilation_blob_name(year, month, time_filter)

    # Check if compilation already exists
    if not force_regenerate:
        existing = check_compilation_exists(storage_client, bucket_name, blob_name)
        if existing.get("exists"):
            logging.info(f"Using cached compilation: {blob_name}")
            # Check for existing thumbnail
            thumb_blob_name = get_thumbnail_blob_name(year, month, time_filter)
            thumb_url = f"https://storage.googleapis.com/{bucket_name}/{thumb_blob_name}"
            return {
                "url": existing["url"],
                "size_bytes": existing["size_bytes"],
                "thumbnail_url": thumb_url,
                "cached": True,
                "generated_at": existing["updated"],
            }

    # List videos for the month
    video_blobs = list_videos_for_month(storage_client, bucket_name, year, month, time_filter)

    if not video_blobs:
        filter_desc = f" ({time_filter})" if time_filter else ""
        raise ValueError(f"No videos found for {year}/{month:02d}{filter_desc}")

    logging.info(f"Found {len(video_blobs)} videos for compilation")

    # Download, concatenate, and upload
    with tempfile.TemporaryDirectory() as tmp_dir:
        local_paths = []

        # Download all videos
        for blob_name_video in video_blobs:
            local_path = os.path.join(tmp_dir, os.path.basename(blob_name_video))
            download_video_from_gcs(storage_client, bucket_name, blob_name_video, local_path)
            local_paths.append(local_path)

        # Concatenate videos
        output_path = os.path.join(tmp_dir, "compilation.mp4")
        concatenate_videos(local_paths, output_path)

        # Get duration of the compilation
        duration = get_video_duration(output_path)

        # Get file size
        file_size = os.path.getsize(output_path)

        # Upload to GCS
        url = upload_compilation_to_gcs(storage_client, bucket_name, output_path, blob_name)

        # Generate and upload thumbnail
        thumbnail_path = os.path.join(tmp_dir, "thumbnail.jpg")
        thumbnail_url = None
        if extract_thumbnail(output_path, thumbnail_path):
            thumb_blob_name = get_thumbnail_blob_name(year, month, time_filter)
            thumbnail_url = upload_thumbnail_to_gcs(
                storage_client, bucket_name, thumbnail_path, thumb_blob_name
            )

    return {
        "url": url,
        "video_count": len(video_blobs),
        "duration_seconds": duration,
        "size_bytes": file_size,
        "thumbnail_url": thumbnail_url,
        "cached": False,
        "generated_at": datetime.now().isoformat(),
    }


def list_available_months(
    storage_client: storage.Client,
    bucket_name: str,
) -> list[dict]:
    """
    List all months that have videos in the bucket.

    Args:
        storage_client: GCS client instance
        bucket_name: Name of the GCS bucket

    Returns:
        List of dictionaries with year, month, counts, and compilation status
    """
    bucket = storage_client.bucket(bucket_name)

    # Find all year/month prefixes by listing top-level directories
    months_found = set()
    blobs = bucket.list_blobs()

    for blob in blobs:
        if not blob.name.endswith(".mp4"):
            continue
        # Skip compilations and collages
        if "/compilations/" in blob.name or "/collages/" in blob.name:
            continue

        # Extract year/month from path like "2025/01/seacliff-xxx.mp4"
        parts = blob.name.split("/")
        if len(parts) >= 2:
            try:
                year = int(parts[0])
                month = int(parts[1])
                months_found.add((year, month))
            except ValueError:
                continue

    # Get details for each month
    result = []
    for year, month in sorted(months_found, reverse=True):
        counts = get_video_counts_for_month(storage_client, bucket_name, year, month)

        # Check for existing compilations
        sunrise_blob = get_compilation_blob_name(year, month, "sunrise")
        sunset_blob = get_compilation_blob_name(year, month, "sunset")
        all_blob = get_compilation_blob_name(year, month, None)

        has_sunrise = check_compilation_exists(storage_client, bucket_name, sunrise_blob).get("exists", False)
        has_sunset = check_compilation_exists(storage_client, bucket_name, sunset_blob).get("exists", False)
        has_all = check_compilation_exists(storage_client, bucket_name, all_blob).get("exists", False)

        result.append({
            "year": year,
            "month": month,
            "sunrise_count": counts["sunrise_count"],
            "sunset_count": counts["sunset_count"],
            "total_count": counts["total_count"],
            "has_sunrise_compilation": has_sunrise,
            "has_sunset_compilation": has_sunset,
            "has_all_compilation": has_all,
        })

    return result
