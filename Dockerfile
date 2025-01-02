FROM python:3.10-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    procps \
    inetutils-syslogd \
    curl \
    ffmpeg \
    cron \
    at \
    tzdata && \
    pip install yt-dlp google-cloud-storage astral pytz && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Add the cron job to execute sun.py every day at 7 AM
RUN echo "0 7 * * * /usr/bin/python3 /app/sun.py" | crontab -

# Download and install Google Cloud SDK
RUN curl https://sdk.cloud.google.com | bash && \
    /root/google-cloud-sdk/install --quiet && \
    echo "installed"
ENV PATH="$PATH:/root/google-cloud-sdk/bin"

# Set the default timezone to Pacific
RUN ln -sf /usr/share/zoneinfo/America/Los_Angeles /etc/localtime && \
    echo "America/Los_Angeles" > /etc/timezone

# Set the working directory
WORKDIR /app

# Copy application files
COPY sun.py /app/sun.py
COPY save_video.sh /app/save_video.sh
COPY gcloud_upload.sh /app/gcloud_upload.sh
COPY endpoint.sh /app/endpoint.sh

# Ensure scripts have executable permissions
RUN chmod +x /app/*.sh

# Start the container with the endpoint script
CMD ["bash", "/app/endpoint.sh"]
