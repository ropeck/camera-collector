"""
Collage generation module for camera-collector.

This module provides functionality to generate grid collages from multiple
sunrise/sunset videos stored in Google Cloud Storage.
"""

import logging
import os
import subprocess
import tempfile
from datetime import datetime
from typing import Optional

from google.cloud import storage
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

# Approximate times for filtering sunrise vs sunset (in 24h format)
SUNRISE_HOUR_RANGE = (5, 10)  # 5 AM to 10 AM
SUNSET_HOUR_RANGE = (16, 21)  # 4 PM to 9 PM


def list_videos_from_gcs(
    storage_client: storage.Client,
    bucket_name: str,
    year: Optional[int] = None,
    month: Optional[int] = None,
    time_filter: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[str]:
    """
    List video blobs from GCS filtered by date and time of day.

    Args:
        storage_client: GCS client instance
        bucket_name: Name of the GCS bucket
        year: Filter by year (default: current year)
        month: Filter by month (default: current month)
        time_filter: "sunrise" or "sunset" to filter by time of day
        limit: Maximum number of videos to return

    Returns:
        List of blob names matching the filters
    """
    if year is None:
        year = datetime.now().year
    if month is None:
        month = datetime.now().month

    prefix = f"{year}/{month:02d}/"
    bucket = storage_client.bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=prefix)

    video_blobs = []
    for blob in blobs:
        if not blob.name.endswith(".mp4"):
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

        if limit and len(video_blobs) >= limit:
            break

    # Sort by filename (which contains timestamp) for chronological order
    video_blobs.sort()
    return video_blobs


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
        # Extract the timestamp part: seacliff-2025-01-24T14:30-15-0800.mp4
        basename = os.path.basename(filename)
        # Remove prefix and extension
        timestamp_part = basename.replace("seacliff-", "").replace(".mp4", "")
        # Parse the hour from YYYY-MM-DDTHH:MM format
        hour_str = timestamp_part.split("T")[1].split(":")[0]
        return int(hour_str)
    except (IndexError, ValueError):
        return None


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


def extract_frame_from_video(video_path: str, timestamp_sec: float = 7.0) -> Image.Image:
    """
    Extract a single frame from a video using ffmpeg.

    Args:
        video_path: Path to the video file
        timestamp_sec: Time in seconds to extract the frame (default: 7s, middle of 15s video)

    Returns:
        PIL Image of the extracted frame
    """
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
        output_path = tmp_file.name

    try:
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output file
            "-ss", str(timestamp_sec),  # Seek to timestamp
            "-i", video_path,  # Input file
            "-vframes", "1",  # Extract 1 frame
            "-q:v", "2",  # High quality JPEG
            output_path,
        ]
        logging.info(f"Extracting frame: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()}")

        image = Image.open(output_path)
        # Load the image into memory so we can delete the temp file
        image.load()
        return image.copy()
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def create_grid_collage(
    images: list[Image.Image],
    grid_cols: int = 5,
    grid_rows: int = 6,
    thumb_width: int = 384,
    thumb_height: int = 216,
    padding: int = 2,
    background_color: tuple = (0, 0, 0),
) -> Image.Image:
    """
    Create a grid collage from a list of images.

    Args:
        images: List of PIL Images to arrange in the grid
        grid_cols: Number of columns in the grid
        grid_rows: Number of rows in the grid
        thumb_width: Width of each thumbnail
        thumb_height: Height of each thumbnail
        padding: Padding between images
        background_color: Background color as RGB tuple

    Returns:
        PIL Image of the collage
    """
    total_width = grid_cols * thumb_width + (grid_cols + 1) * padding
    total_height = grid_rows * thumb_height + (grid_rows + 1) * padding

    collage = Image.new("RGB", (total_width, total_height), background_color)

    for idx, img in enumerate(images):
        if idx >= grid_cols * grid_rows:
            break

        row = idx // grid_cols
        col = idx % grid_cols

        # Resize image to thumbnail size
        thumb = img.copy()
        thumb.thumbnail((thumb_width, thumb_height), Image.Resampling.LANCZOS)

        # Center the thumbnail if it's not exactly the right size
        x_offset = (thumb_width - thumb.width) // 2
        y_offset = (thumb_height - thumb.height) // 2

        x = padding + col * (thumb_width + padding) + x_offset
        y = padding + row * (thumb_height + padding) + y_offset

        collage.paste(thumb, (x, y))

    return collage


def upload_collage_to_gcs(
    storage_client: storage.Client,
    bucket_name: str,
    collage: Image.Image,
    blob_name: str,
) -> str:
    """
    Upload a collage image to GCS.

    Args:
        storage_client: GCS client instance
        bucket_name: Name of the GCS bucket
        collage: PIL Image to upload
        blob_name: Name for the blob in GCS

    Returns:
        Public URL of the uploaded collage
    """
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
        tmp_path = tmp_file.name

    try:
        collage.save(tmp_path, "JPEG", quality=90)

        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(tmp_path, content_type="image/jpeg")

        logging.info(f"Uploaded collage to {blob_name}")
        return f"https://storage.googleapis.com/{bucket_name}/{blob_name}"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def generate_collage(
    storage_client: storage.Client,
    bucket_name: str,
    year: Optional[int] = None,
    month: Optional[int] = None,
    time_filter: Optional[str] = None,
    grid_cols: int = 5,
    grid_rows: int = 6,
    frame_time: float = 7.0,
) -> dict:
    """
    Generate a grid collage from videos in GCS.

    Args:
        storage_client: GCS client instance
        bucket_name: Name of the GCS bucket
        year: Filter videos by year
        month: Filter videos by month
        time_filter: "sunrise" or "sunset" to filter by time of day
        grid_cols: Number of columns in the grid
        grid_rows: Number of rows in the grid
        frame_time: Seconds into video to extract frame

    Returns:
        Dictionary with collage_url, videos_used, and grid_size
    """
    if year is None:
        year = datetime.now().year
    if month is None:
        month = datetime.now().month

    max_videos = grid_cols * grid_rows

    # List videos from GCS
    logging.info(f"Listing videos from {bucket_name} for {year}/{month:02d}")
    video_blobs = list_videos_from_gcs(
        storage_client,
        bucket_name,
        year=year,
        month=month,
        time_filter=time_filter,
        limit=max_videos,
    )

    if not video_blobs:
        raise ValueError(f"No videos found for {year}/{month:02d} with filter '{time_filter}'")

    logging.info(f"Found {len(video_blobs)} videos")

    # Extract frames from each video
    images = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        for blob_name in video_blobs:
            try:
                local_path = os.path.join(tmp_dir, os.path.basename(blob_name))
                download_video_from_gcs(storage_client, bucket_name, blob_name, local_path)
                frame = extract_frame_from_video(local_path, frame_time)
                images.append(frame)
                # Clean up video file after extracting frame
                os.remove(local_path)
            except Exception as e:
                logging.error(f"Error processing {blob_name}: {e}")
                continue

    if not images:
        raise ValueError("Failed to extract frames from any videos")

    logging.info(f"Extracted {len(images)} frames")

    # Create collage
    collage = create_grid_collage(images, grid_cols, grid_rows)

    # Generate collage filename
    filter_suffix = f"-{time_filter}" if time_filter else ""
    collage_name = f"{year}/{month:02d}/collages/collage-{year}-{month:02d}{filter_suffix}-{grid_cols}x{grid_rows}.jpg"

    # Upload collage
    collage_url = upload_collage_to_gcs(storage_client, bucket_name, collage, collage_name)

    return {
        "collage_url": collage_url,
        "videos_used": len(images),
        "grid_size": f"{grid_cols}x{grid_rows}",
    }
