FROM python:latest

# Set the working directory
WORKDIR /app
COPY requirements.txt /app

# Install dependencies and clean up to keep image size small
RUN apt-get update && apt-get install -y \
    procps \
    inetutils-syslogd \
    curl \
    ffmpeg \
    cron \
    at \
    iproute2 \
    iputils-ping \
    tzdata && \
    pip install -r requirements.txt && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Add the cron job to execute sun.py every day at 5 AM before sunrise
RUN echo "0 5 * * * /app/sun.py" | crontab -

# Download and install Google Cloud SDK
RUN curl https://sdk.cloud.google.com | bash && \
    echo "gcloud sdk installed"
ENV PATH="$PATH:/root/google-cloud-sdk/bin"

# Set the default timezone to Pacific
RUN ln -sf /usr/share/zoneinfo/America/Los_Angeles /etc/localtime && \
    echo "America/Los_Angeles" > /etc/timezone


# Copy application files
COPY app.py /app/app.py
COPY sun.py /app/sun.py
COPY start_collection.py /app/start_collection.py
COPY endpoint.sh /app/endpoint.sh

# Ensure scripts have executable permissions
RUN chmod +x /app/*.sh /app/*.py

# Start the container with the endpoint script
CMD ["bash", "/app/endpoint.sh"]
