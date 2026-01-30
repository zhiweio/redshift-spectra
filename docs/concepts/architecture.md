# Architecture

This document provides a comprehensive overview of Redshift Spectra's architecture, explaining the design decisions that make it suitable for enterprise data platforms.

## Design Philosophy

Redshift Spectra is built on three fundamental principles:

1. **Security by Design** — Tenant isolation is enforced at the database layer, not in application code
2. **Serverless First** — No servers to manage, automatic scaling, pay-per-use pricing
3. **Enterprise Ready** — Built for compliance, auditability, and operational excellence

## System Overview

The architecture follows a layered approach where each layer has a specific responsibility:

```mermaid
flowchart TB
    subgraph Clients["Data Consumers"]
        direction LR
        APP[Applications]
        BI[BI Tools]
        ETL[ETL Pipelines]
        PARTNER[Partners]
    end

    subgraph Edge["Edge Layer"]
        WAF[AWS WAF<br/>DDoS Protection]
        APIGW[API Gateway<br/>Rate Limiting · Throttling]
    end

    subgraph Security["Security Layer"]
        AUTHORIZER[Lambda Authorizer<br/>JWT · API Key · IAM]
        CONTEXT[Tenant Context<br/>Extraction & Validation]
    end

    subgraph Compute["Compute Layer"]
        QUERY[Query Handler<br/>Synchronous Execution]
        BULK[Bulk Handler<br/>Async Operations]
        RESULT[Result Handler<br/>Data Retrieval]
        STATUS[Status Handler<br/>Job Monitoring]
    end

    subgraph State["State Management"]
        DDB[(DynamoDB<br/>Jobs · Sessions)]
        CACHE[Session Cache<br/>Connection Reuse]
    end

    subgraph Storage["Storage Layer"]
        S3[(Amazon S3<br/>Large Results)]
    end

    subgraph Data["Data Layer"]
        RS[(Amazon Redshift<br/>RLS · RBAC · Encryption)]
        SM[Secrets Manager<br/>Credential Rotation]
    end

    subgraph Observe["Observability"]
        CW[CloudWatch<br/>Logs · Metrics · Alarms]
        XRAY[X-Ray<br/>Distributed Tracing]
    end

    Clients --> WAF
    WAF --> APIGW
    APIGW --> AUTHORIZER
    AUTHORIZER --> CONTEXT
    CONTEXT --> QUERY
    CONTEXT --> BULK
    CONTEXT --> RESULT
    CONTEXT --> STATUS
    
    QUERY --> DDB
    QUERY --> RS
    BULK --> DDB
    BULK --> S3
    BULK --> RS
    RESULT --> DDB
    RESULT --> S3
    STATUS --> DDB
    
    QUERY --> CACHE
    CACHE --> DDB
    RS --> SM
    
    QUERY --> CW
    BULK --> CW
    QUERY --> XRAY
    BULK --> XRAY
```

## Layer-by-Layer Explanation

### Edge Layer

The edge layer is your first line of defense and traffic management.

**AWS WAF** provides protection against common web exploits:

- SQL injection attempts (additional layer on top of our SQL validator)
- Cross-site scripting (XSS) protection
- Rate-based rules for DDoS mitigation
- Geographic restrictions for compliance

**API Gateway** handles traffic management:

- Request/response transformation
- Per-tenant throttling limits
- Request validation before Lambda invocation
- API versioning support

!!! info "Why API Gateway?"
    We chose API Gateway over Application Load Balancer for its native integration with Lambda authorizers, built-in request validation, and usage plan features essential for multi-tenant platforms.

### Security Layer

The security layer authenticates requests and establishes tenant context.

```mermaid
sequenceDiagram
    participant C as Client
    participant A as Authorizer
    participant H as Handler

    C->>A: Request + Credentials
    A->>A: Validate Token/Key
    A->>A: Extract Tenant Context
    A->>A: Determine Permissions
    A-->>H: IAM Policy + Context
    Note over H: Tenant context includes:<br/>- tenant_id<br/>- db_user<br/>- db_group<br/>- permissions
```

The **Lambda Authorizer** performs several critical functions:

1. **Authentication** — Validates JWT tokens, API keys, or IAM signatures
2. **Context Extraction** — Extracts tenant identifier from the credential
3. **User Mapping** — Maps tenant to appropriate database user
4. **Permission Assignment** — Determines what operations the tenant can perform

!!! warning "Why Tenant Context Matters"
    The tenant context flows through the entire request lifecycle. It determines which Redshift database user executes the query, which in turn controls what data the tenant can access through Row-Level Security.

### Compute Layer

The compute layer contains the business logic, organized into specialized handlers:

| Handler | Purpose | Execution Model |
|---------|---------|-----------------|
| **Query Handler** | Interactive queries | Synchronous (max 5 min) |
| **Bulk Handler** | Large data operations | Asynchronous (up to 24h) |
| **Result Handler** | Data retrieval | Synchronous |
| **Status Handler** | Job monitoring | Synchronous |

**Why Two Execution Models?**

Different use cases have different requirements:

```mermaid
flowchart LR
    subgraph Interactive["Interactive Workloads"]
        DASH[Dashboards]
        REPORT[Reports]
        ADHOC[Ad-hoc Queries]
    end
    
    subgraph Batch["Batch Workloads"]
        ETL[ETL Jobs]
        EXPORT[Data Exports]
        IMPORT[Bulk Imports]
    end
    
    Interactive --> QUERY[Query API<br/>Sync, <5 min]
    Batch --> BULK[Bulk API<br/>Async, <24h]
```

The **Query API** is optimized for:

- Low latency responses
- Interactive user experiences
- Dashboard-style queries
- Small to medium result sets

The **Bulk API** is optimized for:

- Large data volumes
- Long-running operations
- ETL workloads
- Data import/export

### State Management

DynamoDB provides persistent state management with two primary tables:

**Jobs Table** — Tracks all query executions:

- Job metadata (ID, tenant, status, timestamps)
- Execution details (statement ID, duration)
- Result references (S3 location, row counts)
- Audit information (original SQL, parameters)

**Sessions Table** — Manages Redshift Data API sessions:

- Active session tracking per tenant/user combination
- TTL for automatic cleanup
- Last-used timestamps for session reuse

!!! tip "Why DynamoDB?"
    DynamoDB's single-digit millisecond latency and automatic scaling make it ideal for job state management. The built-in TTL feature handles automatic cleanup of old job records.

### Storage Layer

Amazon S3 stores large query results that exceed inline response limits:

- Results are partitioned by tenant for isolation
- Lifecycle rules automatically clean up old results
- Server-side encryption protects data at rest
- Presigned URLs provide time-limited, secure access

### Data Layer

**Amazon Redshift** is the analytical engine:

- Row-Level Security (RLS) enforces tenant data isolation
- Role-Based Access Control (RBAC) manages permissions
- Encryption at rest with KMS
- Audit logging for compliance

**Secrets Manager** handles credentials:

- Automatic rotation of database credentials
- No hardcoded passwords in code or configuration
- IAM-based access control

## Data Flow Patterns

### Synchronous Query Flow

The Query API executes queries synchronously, returning results directly in the response:

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant GW as API Gateway
    participant A as Authorizer
    participant H as Query Handler
    participant D as DynamoDB
    participant RS as Redshift

    C->>GW: POST /queries
    GW->>A: Authorize
    A-->>GW: Allow + Context
    GW->>H: Invoke
    
    H->>H: Validate SQL
    H->>H: Inject LIMIT
    H->>D: Create Job
    H->>RS: Execute Statement
    
    loop Poll (max 5 min)
        H->>RS: Describe Statement
        RS-->>H: Status
    end
    
    H->>RS: Get Results
    RS-->>H: Data
    H->>D: Update Job
    H-->>C: Response with Data
```

Key design decisions:

1. **LIMIT Injection** — Automatically adds LIMIT clause to prevent memory issues
2. **Polling with Backoff** — Exponential backoff prevents API throttling
3. **Truncation Detection** — Returns partial data with warning if results exceed threshold
4. **Job Audit Trail** — Every query is recorded even for sync execution

### Asynchronous Bulk Flow

The Bulk API uses a job-based pattern for long-running operations:

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant H as Bulk Handler
    participant D as DynamoDB
    participant S as S3
    participant RS as Redshift

    C->>H: POST /bulk/jobs
    H->>D: Create Job (Open)
    H-->>C: Job ID + Upload URL
    
    C->>S: Upload Data
    C->>H: PATCH /bulk/jobs/{id}
    H->>D: Update (UploadComplete)
    
    Note over H,RS: Background Processing
    
    H->>RS: Execute Query/COPY
    RS-->>H: Results
    H->>S: Write Results
    H->>D: Update (Complete)
    
    C->>H: GET /bulk/jobs/{id}
    H-->>C: Status + Download URL
```

Key design decisions:

1. **State Machine** — Clear job states (Open → UploadComplete → InProgress → Complete)
2. **Decoupled Upload** — Presigned URLs allow direct S3 upload without Lambda
3. **Background Processing** — Jobs continue processing after client disconnects
4. **Result Delivery** — Large results stored in S3 with secure presigned URLs

## Scalability Considerations

### Horizontal Scaling

```mermaid
flowchart LR
    subgraph Requests["Concurrent Requests"]
        R1[Request 1]
        R2[Request 2]
        R3[Request N]
    end
    
    subgraph Lambda["Lambda Auto-Scaling"]
        L1[Instance 1]
        L2[Instance 2]
        L3[Instance N]
    end
    
    subgraph Redshift["Redshift Concurrency"]
        RS[(Redshift<br/>WLM Queues)]
    end
    
    Requests --> Lambda
    Lambda --> RS
```

- **Lambda** — Automatically scales to thousands of concurrent executions
- **DynamoDB** — On-demand capacity scales with traffic
- **S3** — Virtually unlimited storage capacity
- **Redshift** — WLM queues manage concurrent queries

### Performance Optimizations

1. **Session Reuse** — Redshift Data API sessions are cached and reused
2. **Connection Pooling** — Sessions are shared across requests for the same tenant
3. **Lambda Warm Start** — Provisioned concurrency for latency-sensitive workloads
4. **Smart Caching** — Session metadata cached in DynamoDB with TTL

## Deployment Architecture

Redshift Spectra supports multiple deployment topologies:

### Single-Region Deployment

Suitable for most use cases:

```mermaid
flowchart TB
    subgraph Region["AWS Region"]
        APIGW[API Gateway]
        LAMBDA[Lambda]
        DDB[(DynamoDB)]
        S3[(S3)]
        RS[(Redshift)]
    end
    
    CLIENTS[Clients] --> APIGW
```

### Multi-Region Deployment

For global enterprises requiring low-latency access:

```mermaid
flowchart TB
    subgraph Primary["Primary Region"]
        APIGW1[API Gateway]
        LAMBDA1[Lambda]
        RS1[(Redshift)]
        DDB1[(DynamoDB)]
    end
    
    subgraph Secondary["Secondary Region"]
        APIGW2[API Gateway]
        LAMBDA2[Lambda]
        DDB2[(DynamoDB)]
    end
    
    R53[Route 53] --> APIGW1
    R53 --> APIGW2
    DDB1 <-.->|Global Tables| DDB2
    RS1 -.->|Data Sharing| Secondary
```

## Next Steps

Now that you understand the architecture:

- [Learn about multi-tenancy](multi-tenancy.md) — Deep dive into tenant isolation
- [Explore data delivery](data-delivery.md) — Understand result handling strategies
- [Review security model](../security/overview.md) — Comprehensive security overview
