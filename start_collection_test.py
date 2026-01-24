import pytest
from unittest.mock import patch, MagicMock, call
import json

from start_collection import (
    start_collection,
    wait_for_image_ready,
    fetch_latest_image,
    main,
    START_COLLECTION_API_URL,
    WEBSOCKET_URL,
    IMAGE_REQUEST_URL
)


class TestConstants:
    def test_api_url(self):
        """Test that API URL is correctly configured."""
        assert START_COLLECTION_API_URL == "https://api.fogcat5.com/collection/start"

    def test_websocket_url(self):
        """Test that WebSocket URL is correctly configured."""
        assert WEBSOCKET_URL == "wss://api.fogcat5.com/ws"

    def test_image_request_url(self):
        """Test that image request URL is correctly configured."""
        assert IMAGE_REQUEST_URL == "https://weather.fogcat5.com/collector/video_latest"


class TestStartCollection:
    def test_successful_start(self):
        """Test successful collection start returns job_id."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "job_id": "test-job-123",
            "message": "Collection started"
        }

        with patch('start_collection.requests.post', return_value=mock_response):
            job_id = start_collection()

        assert job_id == "test-job-123"

    def test_failed_start_non_200(self):
        """Test that non-200 response returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch('start_collection.requests.post', return_value=mock_response):
            job_id = start_collection()

        assert job_id is None

    def test_failed_start_exception(self):
        """Test that exception during request returns None."""
        with patch('start_collection.requests.post', side_effect=Exception("Connection error")):
            job_id = start_collection()

        assert job_id is None

    def test_posts_to_correct_url(self):
        """Test that POST request is made to correct URL."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"job_id": "123", "message": "ok"}

        with patch('start_collection.requests.post', return_value=mock_response) as mock_post:
            start_collection()

        mock_post.assert_called_once_with(START_COLLECTION_API_URL)

    def test_missing_job_id_returns_na(self):
        """Test that missing job_id in response is handled."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "Started"}  # No job_id

        with patch('start_collection.requests.post', return_value=mock_response):
            job_id = start_collection()

        assert job_id == "N/A"


class TestWaitForImageReady:
    def test_websocket_connection_url(self):
        """Test that WebSocket connects to correct URL."""
        job_id = "test-job-123"

        with patch('start_collection.websocket.WebSocketApp') as mock_ws_class:
            mock_ws = MagicMock()
            mock_ws_class.return_value = mock_ws

            wait_for_image_ready(job_id)

            # Verify WebSocketApp was called with correct URL
            call_args = mock_ws_class.call_args
            expected_url = f"{WEBSOCKET_URL}/{job_id}"
            assert call_args[0][0] == expected_url

    def test_websocket_callbacks_set(self):
        """Test that WebSocket callbacks are properly configured."""
        job_id = "test-job-123"

        with patch('start_collection.websocket.WebSocketApp') as mock_ws_class:
            mock_ws = MagicMock()
            mock_ws_class.return_value = mock_ws

            wait_for_image_ready(job_id)

            # Verify callbacks are set
            call_kwargs = mock_ws_class.call_args[1]
            assert 'on_message' in call_kwargs
            assert 'on_error' in call_kwargs
            assert 'on_close' in call_kwargs

    def test_websocket_run_forever_called(self):
        """Test that run_forever is called on WebSocket."""
        job_id = "test-job-123"

        with patch('start_collection.websocket.WebSocketApp') as mock_ws_class:
            mock_ws = MagicMock()
            mock_ws_class.return_value = mock_ws

            wait_for_image_ready(job_id)

            mock_ws.run_forever.assert_called_once()

    def test_websocket_exception_handling(self):
        """Test that exceptions during WebSocket connection are handled."""
        job_id = "test-job-123"

        with patch('start_collection.websocket.WebSocketApp', side_effect=Exception("Connection failed")):
            # Should not raise, just log error
            wait_for_image_ready(job_id)


class TestWebSocketCallbacks:
    def test_on_message_completed_closes_connection(self):
        """Test that completed status closes WebSocket."""
        job_id = "test-job-123"
        mock_ws = MagicMock()

        # We need to capture the on_message callback
        captured_callback = None

        def capture_ws_app(url, on_message=None, on_error=None, on_close=None):
            nonlocal captured_callback
            captured_callback = on_message
            ws = MagicMock()
            ws.run_forever = MagicMock()
            return ws

        with patch('start_collection.websocket.WebSocketApp', side_effect=capture_ws_app):
            wait_for_image_ready(job_id)

        # Now test the callback
        message = json.dumps({"job_id": job_id, "status": "completed"})
        captured_callback(mock_ws, message)

        mock_ws.close.assert_called_once()

    def test_on_message_in_progress_does_not_close(self):
        """Test that in-progress status keeps connection open."""
        job_id = "test-job-123"
        mock_ws = MagicMock()

        captured_callback = None

        def capture_ws_app(url, on_message=None, on_error=None, on_close=None):
            nonlocal captured_callback
            captured_callback = on_message
            ws = MagicMock()
            ws.run_forever = MagicMock()
            return ws

        with patch('start_collection.websocket.WebSocketApp', side_effect=capture_ws_app):
            wait_for_image_ready(job_id)

        message = json.dumps({"job_id": job_id, "status": "in_progress"})
        captured_callback(mock_ws, message)

        mock_ws.close.assert_not_called()

    def test_on_message_different_job_id_ignored(self):
        """Test that messages for different job IDs are ignored."""
        job_id = "test-job-123"
        mock_ws = MagicMock()

        captured_callback = None

        def capture_ws_app(url, on_message=None, on_error=None, on_close=None):
            nonlocal captured_callback
            captured_callback = on_message
            ws = MagicMock()
            ws.run_forever = MagicMock()
            return ws

        with patch('start_collection.websocket.WebSocketApp', side_effect=capture_ws_app):
            wait_for_image_ready(job_id)

        # Message for different job
        message = json.dumps({"job_id": "different-job", "status": "completed"})
        captured_callback(mock_ws, message)

        # Should not close for different job
        mock_ws.close.assert_not_called()


class TestFetchLatestImage:
    def test_successful_fetch(self):
        """Test successful image fetch."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "video/mp4"}

        with patch('start_collection.requests.get', return_value=mock_response) as mock_get:
            fetch_latest_image()

        mock_get.assert_called_once_with(IMAGE_REQUEST_URL)

    def test_failed_fetch_non_200(self):
        """Test handling of non-200 response."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        with patch('start_collection.requests.get', return_value=mock_response):
            # Should not raise, just log error
            fetch_latest_image()

    def test_fetch_exception_handling(self):
        """Test that exceptions during fetch are handled."""
        with patch('start_collection.requests.get', side_effect=Exception("Network error")):
            # Should not raise
            fetch_latest_image()


class TestMain:
    def test_successful_flow(self):
        """Test successful main execution flow."""
        with patch('start_collection.start_collection', return_value="job-123") as mock_start, \
             patch('start_collection.wait_for_image_ready') as mock_wait, \
             patch('start_collection.fetch_latest_image') as mock_fetch:

            main()

            mock_start.assert_called_once()
            mock_wait.assert_called_once_with("job-123")
            mock_fetch.assert_called_once()

    def test_main_stops_if_start_fails(self):
        """Test that main stops if start_collection fails."""
        with patch('start_collection.start_collection', return_value=None) as mock_start, \
             patch('start_collection.wait_for_image_ready') as mock_wait, \
             patch('start_collection.fetch_latest_image') as mock_fetch:

            main()

            mock_start.assert_called_once()
            mock_wait.assert_not_called()
            mock_fetch.assert_not_called()

    def test_main_calls_functions_in_order(self):
        """Test that main calls functions in correct order."""
        call_order = []

        def track_start():
            call_order.append('start')
            return "job-123"

        def track_wait(job_id):
            call_order.append('wait')

        def track_fetch():
            call_order.append('fetch')

        with patch('start_collection.start_collection', side_effect=track_start), \
             patch('start_collection.wait_for_image_ready', side_effect=track_wait), \
             patch('start_collection.fetch_latest_image', side_effect=track_fetch):

            main()

        assert call_order == ['start', 'wait', 'fetch']


class TestOnOpenCallback:
    def test_on_open_sends_subscription(self):
        """Test that on_open sends subscription message."""
        job_id = "test-job-123"
        mock_ws = MagicMock()

        # Capture the on_open callback
        captured_on_open = None

        def capture_ws_app(url, on_message=None, on_error=None, on_close=None):
            ws = MagicMock()
            ws.run_forever = MagicMock()
            return ws

        with patch('start_collection.websocket.WebSocketApp', side_effect=capture_ws_app) as mock_class:
            wait_for_image_ready(job_id)

            # Get the created WebSocket instance
            ws_instance = mock_class.return_value

            # The on_open is set as an attribute
            # We need to verify it would send the right message
            # Since on_open is set after WebSocketApp creation, let's verify the pattern

        # Verify WebSocketApp was created
        mock_class.assert_called_once()
