# AI Dashboard Interface Contract

## Overview
This document defines the minimal API contract for the Operations AI Assistant front-end and its supporting API routes.

## Endpoints

### POST /api/upload
Uploads a data file (Excel or CSV) and returns an upload ID.

Request:
- Content-Type: multipart/form-data
- Fields:
  - file: required

Response (200):
```json
{
  "uploadId": "string",
  "filename": "string",
  "rowCount": 120,
  "columnCount": 8
}
```

Response (4xx/5xx):
```json
{
  "error": "string"
}
```

### POST /api/chat
Submits a chat message with optional upload reference and returns a streaming response.

Request (JSON):
```json
{
  "messages": [{ "role": "user", "content": "string" }],
  "uploadId": "string|null"
}
```

Response:
- Streaming text response (SSE)
- Additional data payloads may include table, chart, and report metadata.

### GET /api/report/{id}
Downloads a generated report file.

Response:
- 200 OK with file attachment
- 404 if report not found

## Data Payload Schema
Data payloads sent alongside chat streaming responses:

```json
{
  "tables": [
    {
      "title": "string",
      "headers": ["string"],
      "rows": [["string"]]
    }
  ],
  "charts": [
    {
      "title": "string",
      "labels": ["string"],
      "values": [0]
    }
  ],
  "report": {
    "id": "string",
    "filename": "string"
  }
}
```
