# Data Delivery

Redshift Spectra provides intelligent data delivery that automatically adapts to result size, ensuring optimal performance for both small interactive queries and large data exports.

## Delivery Strategy Overview

```mermaid
flowchart TB
    QUERY[Query Executed] --> SIZE{Result Size?}

    SIZE -->|"< Threshold"| INLINE[Inline JSON<br/>Direct response]
    SIZE -->|"> Threshold<br/>(Query API)"| TRUNCATE[Truncated Inline<br/>With warning]
    SIZE -->|"Any Size<br/>(Bulk API)"| S3[S3 Export<br/>Presigned URL]

    INLINE --> CLIENT[Client]
    TRUNCATE --> CLIENT
    S3 --> CLIENT
```

The delivery method depends on the API used and result size:

| API | Small Results | Large Results |
|-----|--------------|---------------|
| **Query API** | Inline JSON | Truncated + warning |
| **Bulk API** | S3 export | S3 export |

## Query API: Inline Delivery

The Query API returns results directly in the response body for fast, interactive access.

### Synchronous Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant H as Handler
    participant RS as Redshift

    C->>H: POST /v1/queries
    H->>RS: Execute Query
    RS-->>H: Results

    alt Results <= Threshold
        H-->>C: {data: [...], truncated: false}
    else Results > Threshold
        H->>H: Truncate to threshold
        H-->>C: {data: [...], truncated: true, message: "..."}
    end
```

### Inline Response Structure

Inline responses include both data and metadata:

```mermaid
classDiagram
    class QueryResponse {
        +string job_id
        +string status
        +list data
        +ResultMetadata metadata
    }

    class ResultMetadata {
        +list columns
        +int row_count
        +bool truncated
        +int execution_time_ms
        +string message
    }

    QueryResponse --> ResultMetadata
```

### Truncation Behavior

When results exceed the threshold, the Query API:

1. Fetches `threshold + 1` rows
2. Detects if there are more rows
3. Returns only `threshold` rows
4. Sets `truncated: true` with guidance message

```mermaid
flowchart TB
    subgraph Strategy["LIMIT+1 Strategy"]
        direction TB

        INJECT["Inject LIMIT (threshold+1)"] --> EXEC["Execute Query"]
        EXEC --> CHECK{Returned threshold+1?}

        CHECK -->|Yes| TRUNC["Return threshold rows<br/>truncated: true"]
        CHECK -->|No| FULL["Return all rows<br/>truncated: false"]
    end
```

This strategy detects truncation without executing the query twice.

## Bulk API: S3 Delivery

The Bulk API exports results directly to Amazon S3, supporting unlimited result sizes.

### Asynchronous Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant H as Handler
    participant RS as Redshift
    participant S3 as Amazon S3

    C->>H: POST /v1/bulk
    H->>H: Create Job
    H-->>C: {job_id, status: "PENDING"}

    H->>RS: Execute Query (async)
    RS->>S3: UNLOAD to S3
    H->>H: Monitor Progress

    C->>H: GET /v1/bulk/{job_id}
    H-->>C: {status: "RUNNING", progress: 50%}

    RS-->>H: Complete
    H->>S3: Generate Presigned URL

    C->>H: GET /v1/bulk/{job_id}
    H-->>C: {status: "COMPLETED", download_url: "..."}

    C->>S3: Download Results
    S3-->>C: Data File
```

### Export Formats

The Bulk API supports multiple export formats:

```mermaid
flowchart LR
    subgraph Formats["Supported Formats"]
        direction TB

        JSON["JSON<br/>Universal compatibility"]
        CSV["CSV<br/>Spreadsheet friendly"]
        PARQUET["Parquet<br/>Analytics optimized"]
    end

    subgraph Compression["Compression Options"]
        direction TB

        GZIP["GZIP<br/>Best compression"]
        ZSTD["ZSTD<br/>Faster decompression"]
        NONE["None<br/>Direct access"]
    end

    Formats --> Compression
```

| Format | Best For | Compression Support |
|--------|----------|-------------------|
| **JSON** | APIs, web applications | GZIP, ZSTD |
| **CSV** | Spreadsheets, simple ETL | GZIP, ZSTD |
| **Parquet** | Data lakes, analytics | Native compression |

### S3 Organization

Results are organized in S3 by tenant and job:

```mermaid
flowchart TB
    subgraph S3["S3 Bucket Structure"]
        direction TB

        BUCKET["s3://spectra-results/"]
        TENANT["tenant-{id}/"]
        JOB["job-{id}/"]
        FILES["data.json<br/>data.csv<br/>data.parquet"]

        BUCKET --> TENANT --> JOB --> FILES
    end
```

This structure ensures:

- **Tenant isolation** — Each tenant has separate prefix
- **IAM policies** — Can restrict access by prefix
- **Lifecycle rules** — Automatic cleanup after retention period

### Presigned URLs

Results are delivered via time-limited presigned URLs:

```mermaid
sequenceDiagram
    participant C as Client
    participant H as Handler
    participant S3 as Amazon S3

    C->>H: GET /v1/bulk/{job_id}
    H->>S3: Generate Presigned URL
    S3-->>H: URL (expires in 1h)
    H-->>C: {download_url: "https://..."}

    C->>S3: GET download_url
    Note over S3: Validate signature<br/>Check expiration
    S3-->>C: Data file
```

Presigned URL characteristics:

- **Time-limited** — Default 1 hour expiration
- **Single-use** — Can optionally restrict to one download
- **Tenant-scoped** — URL only works for original tenant's data
- **No credentials needed** — Client doesn't need AWS credentials

## Choosing the Right API

```mermaid
flowchart TB
    START[Data Need] --> Q1{Interactive?}

    Q1 -->|Yes| Q2{Expected rows?}
    Q1 -->|No| BULK[Use Bulk API]

    Q2 -->|"< 10,000"| QUERY[Use Query API]
    Q2 -->|"> 10,000"| Q3{Need complete data?}

    Q3 -->|Yes| BULK
    Q3 -->|No| QUERY

    QUERY --> INLINE[Inline JSON delivery]
    BULK --> S3[S3 export delivery]
```

### Decision Matrix

| Scenario | API | Delivery | Reason |
|----------|-----|----------|--------|
| Dashboard widget | Query | Inline | Fast, interactive |
| Ad-hoc exploration | Query | Inline | Quick feedback |
| Large report export | Bulk | S3 | Unlimited size |
| ETL pipeline | Bulk | S3 | Reliable, resumable |
| API integration | Query | Inline | Simple consumption |
| Data lake feed | Bulk | S3/Parquet | Optimal format |

## Performance Characteristics

### Inline Delivery

- **Latency**: Low (included in response)
- **Memory**: Limited by Lambda memory
- **Throughput**: Limited by API Gateway payload size
- **Max size**: Configurable threshold (default 10,000 rows)

### S3 Delivery

- **Latency**: Higher (async processing)
- **Memory**: Unlimited (streams to S3)
- **Throughput**: High (parallel UNLOAD)
- **Max size**: Unlimited

```mermaid
xychart-beta
    title "Delivery Method Comparison"
    x-axis ["100 rows", "1K rows", "10K rows", "100K rows", "1M rows"]
    y-axis "Response Time (s)" 0 --> 60
    bar [0.5, 0.8, 2, 0, 0]
    line [2, 3, 5, 15, 45]
```

*Bar = Query API (Inline), Line = Bulk API (S3)*

## Data Format Details

### JSON Format

```json
{
  "metadata": {
    "columns": [...],
    "row_count": 1000,
    "generated_at": "2026-01-30T10:00:00Z"
  },
  "data": [
    {"id": 1, "name": "Product A", "price": 29.99},
    {"id": 2, "name": "Product B", "price": 49.99}
  ]
}
```

### CSV Format

```csv
id,name,price
1,Product A,29.99
2,Product B,49.99
```

CSV options:
- Delimiter: `,` (default), `|`, `\t`
- Quote character: `"` (default)
- Line ending: `\n` (default), `\r\n`
- Header row: Included by default

### Parquet Format

Parquet provides columnar storage with:
- **Schema preservation** — Types preserved from Redshift
- **Compression** — Native compression (Snappy, ZSTD)
- **Partitioning** — Can be partitioned by columns
- **Analytics optimized** — Efficient for BI tools

## Best Practices

!!! tip "Right-Size Your Queries"
    For Query API:

    - Add LIMIT when exploring data
    - Use aggregations to reduce row count
    - Switch to Bulk API for large exports

!!! tip "Choose Format by Consumer"
    - **JSON** for applications and APIs
    - **CSV** for spreadsheets and simple tools
    - **Parquet** for data lakes and analytics

!!! tip "Handle Truncation Gracefully"
    When `truncated: true`:

    - Display partial data with clear indicator
    - Offer option to export full dataset via Bulk API
    - Log for analytics on query patterns

!!! warning "Presigned URL Security"
    Treat presigned URLs like temporary credentials:

    - Don't log URLs with full signatures
    - Use short expiration times
    - Consider single-use restrictions
