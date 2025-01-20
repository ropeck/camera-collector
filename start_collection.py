import requests
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    filename="collection_log.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# API endpoint URL
API_URL = "http://localhost:5000/collection/start"

def start_collection():
    try:
        # Make the POST request to the API
        response = requests.post(API_URL)

        # Check if the request was successful
        if response.status_code == 200:
            data = response.json()
            job_id = data.get("job_id", "N/A")
            message = data.get("message", "No message returned.")
            logging.info(f"Collection started successfully: Job ID: {job_id} - {message}")
        else:
            logging.error(f"Failed to start collection. Status Code: {response.status_code} - {response.text}")

    except Exception as e:
        logging.error(f"An error occurred while starting the collection: {str(e)}")


if __name__ == "__main__":
    start_collection()
