import requests
import websocket
import logging
import json
import time

# API endpoint URLs
START_COLLECTION_API_URL = "https://api.fogcat5.com/collection/start"
WEBSOCKET_URL = "wss://api.fogcat5.com/ws"
IMAGE_REQUEST_URL = "https://weather.fogcat5.com/collector/video_latest"

def start_collection():
    try:
        # Make the POST request to start the collection
        response = requests.post(START_COLLECTION_API_URL)
        if response.status_code == 200:
            data = response.json()
            job_id = data.get("job_id", "N/A")
            message = data.get("message", "No message returned.")
            logging.info(f"Collection started successfully: Job ID: {job_id} - {message}")
            return job_id
        else:
            logging.error(f"Failed to start collection. Status Code: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logging.error(f"An error occurred while starting the collection: {str(e)}")
        return None

def wait_for_image_ready(job_id):
    try:
        def on_message(ws, message):
            data = json.loads(message)
            if data.get("job_id") == job_id and data.get("status") == "ready":
                logging.info(f"Image is ready for Job ID: {job_id}")
                ws.close()  # Close the connection once the image is ready

        def on_error(ws, error):
            logging.error(f"WebSocket error: {error}")

        def on_close(ws, close_status_code, close_msg):
            logging.info("WebSocket connection closed.")

        def on_open(ws):
            logging.info("WebSocket connection opened.")
            # Send a subscription or relevant message if required by the server
            ws.send(json.dumps({"action": "subscribe", "job_id": job_id}))

        # Establish WebSocket connection
        ws = websocket.WebSocketApp(
            f"{WEBSOCKET_URL}/{job_id}",
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        ws.on_open = on_open
        ws.run_forever()
    except Exception as e:
        logging.error(f"An error occurred while waiting for the image to be ready: {str(e)}")

def fetch_latest_image():
    try:
        # Request the image with the text overlay
        response = requests.get(IMAGE_REQUEST_URL)
        if response.status_code == 200:
            logging.info("Successfully fetched the latest image.")
        else:
            logging.error(f"Failed to fetch the latest image. Status Code: {response.status_code} - {response.text}")
    except Exception as e:
        logging.error(f"An error occurred while fetching the latest image: {str(e)}")

def main():
    # Start the collection process
    job_id = start_collection()
    if not job_id:
        logging.error("Collection process failed to start.")
        return

    # Wait for the WebSocket notification that the image is ready
    wait_for_image_ready(job_id)

    # Fetch the latest image from the server
    fetch_latest_image()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
