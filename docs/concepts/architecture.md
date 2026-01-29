# Architecture

Deep dive into the Redshift Spectra system architecture and design decisions.

## System Overview

Redshift Spectra is a serverless middleware that provides secure, multi-tenant access to Amazon Redshift through a RESTful API.

```mermaid
flowchart TB
    subgraph Clients["Data Consumers"]
        direction LR
        APP[Applications]
        BI[BI Tools]
        ETL[ETL Pipelines]
        DASH[Dashboards]
    end

    subgraph AWS["AWS Cloud"]
        subgraph Edge["Edge Layer"]
            APIGW[API Gateway<br/>Rate Limiting, Throttling]
        end

        subgraph Auth["Authorization"]
            AUTHORIZER[Lambda Authorizer<br/>JWT/API Key Validation]
        end

        subgraph Compute["Compute Layer"]
            API[API Handler<br/>Request Processing]
            WORKER[Worker<br/>Async Processing]
        end

        subgraph Layer["Shared Layer"]
            DEPS[Lambda Layer<br/>Dependencies]
        end

        subgraph State["State Management"]
            DDB[(DynamoDB<br/>Jobs & Sessions)]
        end

        subgraph Storage["Storage"]
            S3[(S3<br/>Large Results)]
        end

        subgraph Data["Data Layer"]
            RS[(Redshift<br/>Data Warehouse)]
            SM[Secrets Manager]
        end

        subgraph Observe["Observability"]
            CW[CloudWatch]
            XRAY[X-Ray]
        end
    end

    Clients --> APIGW
    APIGW --> AUTHORIZER
    AUTHORIZER --> API
    API --> DEPS
    WORKER --> DEPS
    API --> DDB
    API --> RS
    WORKER --> DDB
    WORKER --> RS
    WORKER --> S3
    API --> SM
    DDB -.->|Stream| WORKER
    API --> CW
    WORKER --> CW
    API --> XRAY
    WORKER --> XRAY
```

## Core Components

### API Gateway

The entry point for all requests. Provides:

- **Rate Limiting**: Per-tenant request throttling
- **Request Validation**: Schema validation before Lambda invocation
- **CORS**: Cross-origin resource sharing configuration
- **SSL/TLS**: Encrypted communication

### Lambda Authorizer

Validates authentication and extracts tenant context:

```mermaid
flowchart LR
    REQ[Request] --> AUTH{Authorizer}
    AUTH -->|Valid| POLICY[Allow Policy<br/>+ Tenant Context]
    AUTH -->|Invalid| DENY[Deny]
    POLICY --> LAMBDA[Lambda Handler]
```

### API Handler Lambda

Processes incoming requests synchronously:

- Query submission
- Job status checks
- Result retrieval
- Bulk job management

### Worker Lambda

Handles asynchronous operations triggered by DynamoDB Streams:

- Long-running query execution
- Large result export to S3
- Bulk data processing

### Lambda Layer

Shared dependencies for all functions:

| Package | Purpose |
|---------|---------|
| `aws-lambda-powertools` | Logging, tracing, metrics |
| `pydantic` | Data validation |
| `boto3` | AWS SDK |

## Data Flow

### Synchronous Query Flow

For small, fast queries:

```mermaid
sequenceDiagram
    participant Client
    participant API as API Gateway
    participant Handler as API Handler
    participant RS as Redshift
    
    Client->>API: POST /queries
    API->>Handler: Invoke
    Handler->>RS: Execute (Data API)
    RS-->>Handler: Results
    Handler-->>Client: JSON Response
```

### Asynchronous Query Flow

For long-running analytical queries:

```mermaid
sequenceDiagram
    participant Client
    participant API as API Gateway
    participant Handler as API Handler
    participant DDB as DynamoDB
    participant Worker
    participant RS as Redshift
    participant S3
    
    Client->>API: POST /queries {async: true}
    API->>Handler: Invoke
    Handler->>DDB: Create Job (QUEUED)
    Handler-->>Client: {job_id, status: QUEUED}
    
    DDB--)Worker: Stream Trigger
    Worker->>RS: Execute Statement
    Worker->>DDB: Update (RUNNING)
    
    loop Poll Status
        Client->>API: GET /jobs/{id}
        API->>Handler: Get Status
        Handler->>DDB: Query
        Handler-->>Client: {status}
    end
    
    RS-->>Worker: Results
    Worker->>S3: Export Large Results
    Worker->>DDB: Update (COMPLETED)
    
    Client->>API: GET /jobs/{id}/results
    Handler->>S3: Generate Presigned URL
    Handler-->>Client: {download_url}
```

## State Management

### Job Lifecycle

```mermaid
stateDiagram-v2
    [*] --> QUEUED: Submit Query
    QUEUED --> RUNNING: Worker Picks Up
    RUNNING --> COMPLETED: Success
    RUNNING --> FAILED: Error
    QUEUED --> CANCELLED: User Cancel
    RUNNING --> CANCELLED: User Cancel
    COMPLETED --> [*]
    FAILED --> [*]
    CANCELLED --> [*]
```

### DynamoDB Tables

**Jobs Table:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `job_id` (PK) | String | Unique job identifier |
| `tenant_id` (GSI) | String | Tenant identifier |
| `status` | String | Job status |
| `sql` | String | Query SQL |
| `created_at` | String | Creation timestamp |
| `ttl` | Number | Expiration time |

**Sessions Table:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `session_id` (PK) | String | Redshift session ID |
| `tenant_id` (GSI) | String | Tenant identifier |
| `created_at` | String | Session creation time |
| `last_used` | String | Last activity time |
| `ttl` | Number | Expiration time |

## Design Decisions

### Why Redshift Data API?

| Feature | Data API | JDBC/ODBC |
|---------|----------|-----------|
| Connection Management | AWS-managed | Self-managed |
| Scaling | Automatic | Connection pools |
| Cold Start | None | Connection overhead |
| Lambda Compatible | Native | VPC required |

### Why DynamoDB for State?

- **Serverless**: No connection limits
- **Low Latency**: Single-digit millisecond reads
- **Streams**: Trigger async processing
- **TTL**: Automatic data cleanup

### Why Lambda Layer Architecture?

```mermaid
flowchart TB
    subgraph Traditional["Traditional (50MB × 3)"]
        F1[Function 1<br/>Code + Deps]
        F2[Function 2<br/>Code + Deps]
        F3[Function 3<br/>Code + Deps]
    end
    
    subgraph Layer["Layer Architecture (50MB + 3 × ~10KB)"]
        L[Shared Layer<br/>Dependencies]
        L1[Function 1<br/>Code Only]
        L2[Function 2<br/>Code Only]
        L3[Function 3<br/>Code Only]
        L --> L1
        L --> L2
        L --> L3
    end
```

Benefits:

- **Reduced Deployment Size**: Functions are KB instead of MB
- **Faster Updates**: Deploy code without rebuilding dependencies
- **Consistent Versions**: All functions use the same dependency versions

## Scalability

### Request Scaling

```mermaid
flowchart LR
    subgraph Load["Incoming Load"]
        R1[Request 1]
        R2[Request 2]
        R3[Request N]
    end
    
    subgraph Gateway["API Gateway"]
        THROTTLE[Throttling<br/>10,000 RPS]
    end
    
    subgraph Lambda["Lambda"]
        L1[Instance 1]
        L2[Instance 2]
        L3[Instance N]
    end
    
    Load --> THROTTLE
    THROTTLE --> Lambda
```

### Concurrency Limits

| Component | Limit | Configurable |
|-----------|-------|--------------|
| API Gateway | 10,000 RPS | Yes (quota) |
| Lambda Concurrent | 1,000 | Yes (reserved) |
| DynamoDB | On-demand | Automatic |
| Redshift Data API | 200 statements | Account quota |

## Next Steps

- [Multi-Tenancy](multi-tenancy.md) - Tenant isolation design
- [Data Delivery](data-delivery.md) - Result delivery patterns
- [Performance](../performance/overview.md) - Optimization techniques
