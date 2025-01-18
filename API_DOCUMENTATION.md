## **Camera Collector API Documentation**

### **Base URL**
```
http://<your-server-host>:8000
```

---

### **Endpoints**

#### **Health Check**
- **Description**: Check if the API is running.
- **Endpoint**: `GET /`
- **Response**:
  ```json
  {
    "message": "Camera Collector API is running!"
  }
  ```

---

#### **Start a Collection Job**
- **Description**: Start a new video collection job.
- **Endpoint**: `POST /collect`
- **Request Parameters**: None
- **Response**:
  - **Success**:
    ```json
    {
      "job_id": "123e4567-e89b-12d3-a456-426614174000",
      "message": "Collection started with Job ID 123e4567-e89b-12d3-a456-426614174000"
    }
    ```
  - **Fields**:
    - `job_id`: A unique identifier for the collection job. Use this to track the job's progress via WebSocket.
    - `message`: Confirmation message.

---

#### **WebSocket Notifications**
- **Description**: Receive real-time updates about the progress of a specific job.
- **Endpoint**: `ws://<your-server-host>:8000/ws/{job_id}`
- **Path Parameter**:
  - `job_id`: The unique job ID returned from the `/collect` endpoint.
- **Messages**:
  - **On Start**:
    ```text
    Collection started with Job ID: 123e4567-e89b-12d3-a456-426614174000
    ```
  - **Progress Updates**:
    ```text
    Progress: Step 1/5
    Progress: Step 2/5
    ...
    ```
  - **On Completion**:
    ```text
    Collection completed for Job ID: 123e4567-e89b-12d3-a456-426614174000
    ```
  - **On Error**:
    ```text
    Error with Job ID 123e4567-e89b-12d3-a456-426614174000: <error-message>
    ```

---

### **Example Usage**

#### **Start a Collection**
```bash
curl -X POST http://<your-server-host>:8000/collect
```
- **Response**:
  ```json
  {
    "job_id": "123e4567-e89b-12d3-a456-426614174000",
    "message": "Collection started with Job ID 123e4567-e89b-12d3-a456-426614174000"
  }
  ```

---

#### **Connect to WebSocket**
Use a WebSocket client (e.g., [wscat](https://github.com/websockets/wscat)) to connect and receive real-time updates:
```bash
wscat -c ws://<your-server-host>:8000/ws/123e4567-e89b-12d3-a456-426614174000
```

---

### **Planned Enhancements**
1. **Add Parameters to `/collect`**:
   - Support for specifying stream URLs, durations, or custom options.
2. **Enhanced Job Logging**:
   - Save job metadata and logs to a database for historical analysis.
3. **Error Handling**:
   - Retry mechanisms and detailed error reporting.
4. **Analytics Dashboard**:
   - Integrate with tools like Grafana for visualizing collection progress and metrics.

---

### **Dependencies**
- `FastAPI`: High-performance web framework.
- `uvicorn`: ASGI server for running FastAPI applications.

Install dependencies with:
```bash
pip install fastapi uvicorn
```

---

### **Running the Application**
1. Start the API server:
   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8000
   ```
2. Access the API at `http://<your-server-host>:8000`.

---
