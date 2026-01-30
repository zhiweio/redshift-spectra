# API Reference

Complete API reference for Redshift Spectra REST endpoints.

## Base URL

```
https://{api-id}.execute-api.{region}.amazonaws.com/v1
```

## Authentication

All endpoints require authentication via one of:

- `Authorization: Bearer {api_key}` - API Key authentication
- `Authorization: Bearer {jwt_token}` - JWT authentication
- AWS SigV4 - IAM authentication

All endpoints require tenant identification:

- `X-Tenant-ID: {tenant_id}` - Required header

---

## Query API

### Submit Query

Submit a SQL query for execution.

```
POST /queries
```

**Request Headers:**

| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | Bearer token |
| `X-Tenant-ID` | Yes | Tenant identifier |
| `Content-Type` | Yes | `application/json` |

**Request Body:**

```json
{
  "sql": "string",
  "parameters": [
    {
      "name": "string",
      "value": "string"
    }
  ],
  "output_format": "json | csv | parquet",
  "async": true
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `sql` | string | Yes | - | SQL query to execute |
| `parameters` | array | No | `[]` | Query parameters |
| `output_format` | string | No | `json` | Output format |
| `async` | boolean | No | `true` | Async execution |

**Response: `202 Accepted`**

```json
{
  "job_id": "job-abc123def456",
  "status": "QUEUED",
  "submitted_at": "2026-01-29T10:00:00Z"
}
```

---

## Job API

### Get Job Status

Retrieve the status of a submitted job.

```
GET /jobs/{job_id}
```

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `job_id` | string | Job identifier |

**Response: `200 OK`**

```json
{
  "job_id": "job-abc123def456",
  "status": "QUEUED | RUNNING | COMPLETED | FAILED",
  "submitted_at": "2026-01-29T10:00:00Z",
  "started_at": "2026-01-29T10:00:05Z",
  "completed_at": "2026-01-29T10:00:30Z",
  "row_count": 1500,
  "result_location": "inline | s3",
  "error": null
}
```

---

### Get Job Results

Retrieve results for a completed job.

```
GET /jobs/{job_id}/results
```

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `job_id` | string | Job identifier |

**Response: `200 OK` (Inline)**

```json
{
  "data": [
    {"column1": "value1", "column2": 123}
  ],
  "metadata": {
    "columns": ["column1", "column2"],
    "row_count": 1
  }
}
```

**Response: `200 OK` (S3 Export)**

```json
{
  "download_url": "https://s3.amazonaws.com/...",
  "expires_at": "2026-01-29T11:00:00Z",
  "format": "parquet",
  "size_bytes": 52428800
}
```

---

### Cancel Job

Cancel a running job.

```
DELETE /jobs/{job_id}
```

**Response: `200 OK`**

```json
{
  "job_id": "job-abc123def456",
  "status": "CANCELLED",
  "message": "Job cancelled by user"
}
```

---

## Bulk API

### Create Bulk Job

Create a new bulk operation job.

```
POST /bulk/jobs
```

**Request Body:**

```json
{
  "operation": "query | insert | update | upsert | delete",
  "object": "string",
  "content_type": "CSV | JSON",
  "compression": "NONE | GZIP",
  "query": "string"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `operation` | string | Yes | Operation type |
| `object` | string | Yes | Target table name |
| `content_type` | string | No | Data format (default: CSV) |
| `compression` | string | No | Compression type (default: NONE) |
| `query` | string | For query | SQL for query operations |

**Response: `201 Created`**

```json
{
  "job_id": "bulk-job-abc123",
  "state": "Open",
  "operation": "query",
  "object": "sales",
  "created_at": "2026-01-29T10:00:00Z"
}
```

---

### Get Bulk Job

Retrieve bulk job details.

```
GET /bulk/jobs/{job_id}
```

**Response: `200 OK`**

```json
{
  "job_id": "bulk-job-abc123",
  "state": "Open | UploadComplete | InProgress | JobComplete | Failed | Aborted",
  "operation": "query",
  "object": "sales",
  "number_records_processed": 50000,
  "number_records_failed": 12,
  "created_at": "2026-01-29T10:00:00Z",
  "updated_at": "2026-01-29T10:05:00Z"
}
```

---

### Update Bulk Job State

Update job state (e.g., close job to start processing).

```
PATCH /bulk/jobs/{job_id}
```

**Request Body:**

```json
{
  "state": "UploadComplete | Aborted"
}
```

**Response: `200 OK`**

```json
{
  "job_id": "bulk-job-abc123",
  "state": "UploadComplete"
}
```

---

### Get Upload URL

Get presigned URL for data upload.

```
GET /bulk/jobs/{job_id}/upload-url
```

**Response: `200 OK`**

```json
{
  "upload_url": "https://s3.amazonaws.com/...",
  "expires_at": "2026-01-29T11:00:00Z"
}
```

---

### Get Results

Download job results.

```
GET /bulk/jobs/{job_id}/results
```

**Response: `200 OK`**

```json
{
  "download_url": "https://s3.amazonaws.com/...",
  "expires_at": "2026-01-29T11:00:00Z"
}
```

---

### List Bulk Jobs

List bulk jobs for a tenant.

```
GET /bulk/jobs?state={state}&limit={limit}
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `state` | string | - | Filter by state |
| `limit` | integer | 25 | Max results |
| `offset` | string | - | Pagination token |

**Response: `200 OK`**

```json
{
  "jobs": [
    {
      "job_id": "bulk-job-abc123",
      "state": "JobComplete",
      "operation": "query"
    }
  ],
  "next_offset": "eyJsYXN0X2tl..."
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message",
    "details": {}
  }
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INVALID_REQUEST` | 400 | Malformed request |
| `INVALID_SQL` | 400 | SQL syntax error |
| `UNAUTHORIZED` | 401 | Authentication failed |
| `FORBIDDEN` | 403 | Permission denied |
| `NOT_FOUND` | 404 | Resource not found |
| `CONFLICT` | 409 | State conflict |
| `RATE_LIMITED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Server error |

---

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| `POST /queries` | 100/minute |
| `GET /jobs/*` | 300/minute |
| `POST /bulk/jobs` | 10/minute |
| `GET /bulk/jobs/*` | 100/minute |

Rate limit headers:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1738234800
```

---

## SDK Examples

### Python

```python
import requests

class SpectraClient:
    def __init__(self, base_url, api_key, tenant_id):
        self.base_url = base_url
        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'X-Tenant-ID': tenant_id,
            'Content-Type': 'application/json'
        }
    
    def query(self, sql):
        response = requests.post(
            f'{self.base_url}/queries',
            headers=self.headers,
            json={'sql': sql}
        )
        return response.json()
    
    def get_results(self, job_id):
        response = requests.get(
            f'{self.base_url}/jobs/{job_id}/results',
            headers=self.headers
        )
        return response.json()
```

### JavaScript

```javascript
class SpectraClient {
  constructor(baseUrl, apiKey, tenantId) {
    this.baseUrl = baseUrl;
    this.headers = {
      'Authorization': `Bearer ${apiKey}`,
      'X-Tenant-ID': tenantId,
      'Content-Type': 'application/json'
    };
  }

  async query(sql) {
    const response = await fetch(`${this.baseUrl}/queries`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify({ sql })
    });
    return response.json();
  }

  async getResults(jobId) {
    const response = await fetch(
      `${this.baseUrl}/jobs/${jobId}/results`,
      { headers: this.headers }
    );
    return response.json();
  }
}
```
