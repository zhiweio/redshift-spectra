# Redshift Spectra 🚀

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Terraform](https://img.shields.io/badge/terraform-%3E%3D1.11-blueviolet)](https://www.terraform.io/)
[![Terragrunt](https://img.shields.io/badge/terragrunt-%3E%3D0.99-blueviolet)](https://terragrunt.gruntwork.io/)
[![LocalStack](https://img.shields.io/badge/localstack-local%20dev-ff69b4)](https://localstack.cloud/)
[![AWS](https://img.shields.io/badge/AWS-Serverless-orange)](https://aws.amazon.com/)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://zhiweio.github.io/redshift-spectra/)

> **Turn your Amazon Redshift into a secure, multi-tenant Data-as-a-Service platform.**

Redshift Spectra is an enterprise-grade serverless middleware that transforms your Redshift data warehouse into a managed RESTful API. With **zero-trust security**, **database-level tenant isolation**, and **dual execution modes** (synchronous Query API + asynchronous Bulk API), you can safely expose analytical data to internal teams, partners, and customers—without exposing your database directly.

## ✨ Why Redshift Spectra?

Building a multi-tenant data platform is hard. Redshift Spectra solves the key challenges:

```mermaid
flowchart TB
    subgraph Traditional["❌ Traditional Approach"]
        direction TB
        T1[Direct Database Access] --> T2[Security Risks]
        T1 --> T3[Connection Pool Exhaustion]
        T1 --> T4[No Tenant Isolation]
        T1 --> T5[Compliance Violations]
    end

    subgraph Modern["✅ Redshift Spectra"]
        direction TB
        M1[RESTful API Layer] --> M2[Zero-Trust Security]
        M1 --> M3[Serverless Scaling]
        M1 --> M4[Database-Level Isolation]
        M1 --> M5[Full Audit Trail]
    end

    Traditional -.->|"Transform"| Modern
```

| Challenge | Traditional Solution | Redshift Spectra |
|-----------|---------------------|------------------|
| 🔒 **Tenant Isolation** | Application-level filtering (error-prone) | Database-level RLS/RBAC enforcement |
| 🛡️ **Security** | Shared credentials, custom logic | Zero-trust with JWT/API Key/IAM auth |
| ⚡ **Interactive Queries** | Complex async polling | Synchronous API with immediate results |
| 📊 **Large Exports** | Timeout constraints | Async Bulk API with S3 delivery |
| ⏱️ **Latency** | Cold connections every request | Session reuse for 80% latency reduction |
| 🔍 **Compliance** | Custom audit logging | Built-in audit trail with X-Ray tracing |

## 🏗️ Architecture

```mermaid
flowchart TB
    subgraph Consumers["📱 Data Consumers"]
        APP[Internal Apps]
        BI[BI Tools]
        PARTNER[Partner Systems]
        ETL[ETL Pipelines]
    end

    subgraph Spectra["🔐 Redshift Spectra"]
        subgraph Edge["Edge Layer"]
            APIGW[API Gateway<br/>Rate Limiting · WAF]
        end

        subgraph Auth["Authentication"]
            AUTHZ[Authorizer<br/>JWT · API Key · IAM]
        end

        subgraph Compute["Compute Layer"]
            QUERY[Query Handler<br/>Sync Execution]
            BULK[Bulk Handler<br/>Async Operations]
        end

        subgraph State["State Layer"]
            DDB[(DynamoDB<br/>Jobs · Sessions)]
            S3[(S3<br/>Large Results)]
        end
    end

    subgraph Data["🏢 Enterprise Data"]
        RS[(Amazon Redshift<br/>RLS · RBAC)]
    end

    Consumers --> APIGW
    APIGW --> AUTHZ
    AUTHZ --> QUERY
    AUTHZ --> BULK
    QUERY --> DDB
    QUERY --> RS
    BULK --> DDB
    BULK --> S3
    BULK --> RS
```

## 🚀 Quick Start

### Local Development (Recommended)

```bash
# Clone and install
git clone https://github.com/zhiweio/redshift-spectra.git
cd redshift-spectra
task setup:install-dev

# Configure (defaults work for LocalStack)
cp .env.example .env

# Start LocalStack and deploy
task local:deploy

# Verify deployment
task local:status
```

### Query API — Synchronous Execution

For interactive queries with immediate results (≤10,000 rows):

```bash
curl -X POST "https://your-api.execute-api.region.amazonaws.com/v1/queries" \
  -H "Authorization: Bearer $API_KEY" \
  -H "X-Tenant-ID: tenant-a" \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM sales WHERE region = '\''APAC'\'' LIMIT 100"}'
```

Response (immediate):
```json
{
  "data": [
    {"id": 1, "product": "Widget", "amount": 99.99, "region": "APAC"},
    {"id": 2, "product": "Gadget", "amount": 149.99, "region": "APAC"}
  ],
  "metadata": {
    "row_count": 2,
    "column_info": [...],
    "execution_time_ms": 245
  }
}
```

### Bulk API — Asynchronous Execution

For large exports and long-running operations:

```bash
# Create a bulk job
curl -X POST "https://your-api.execute-api.region.amazonaws.com/v1/bulk/jobs" \
  -H "Authorization: Bearer $API_KEY" \
  -H "X-Tenant-ID: tenant-a" \
  -H "Content-Type: application/json" \
  -d '{"operation": "query", "sql": "SELECT * FROM large_table"}'

# Response: {"job_id": "job-abc123", "state": "QUEUED"}

# Poll for completion
curl "https://your-api.execute-api.region.amazonaws.com/v1/bulk/jobs/job-abc123" \
  -H "Authorization: Bearer $API_KEY" \
  -H "X-Tenant-ID: tenant-a"

# When complete, get results via presigned S3 URL
curl "https://your-api.execute-api.region.amazonaws.com/v1/bulk/jobs/job-abc123/result"
```

## 🎯 Key Features

### 🔐 Zero-Trust Security
- **Database-level isolation** — Tenant security enforced by Redshift RLS/RBAC, not application code
- **Multiple auth methods** — JWT tokens, API keys, AWS IAM (SigV4)
- **SQL injection prevention** — Built-in validator blocks dangerous operations
- **Complete audit trail** — Every query logged with tenant context and X-Ray tracing

### ⚡ Dual Execution Modes
- **Query API (Sync)** — Immediate results for interactive workloads, ≤10,000 rows
- **Bulk API (Async)** — Background processing for large exports, unlimited rows
- **Automatic LIMIT injection** — Query API enforces safe result sizes

### 🚀 Performance Optimized
- **Session Reuse** — Redshift Data API `SessionKeepAliveSeconds` for connection pooling
- **CSV Format Parsing** — `get_statement_result_v2` with 70%+ faster deserialization
- **Lambda Layers** — Shared dependencies for faster cold starts

### 📦 Intelligent Data Delivery
- **Inline JSON** — Small results returned directly in API response
- **S3 Presigned URLs** — Large results exported to S3 (Parquet/CSV)
- **Automatic switching** — Threshold-based format selection

### 🔧 Enterprise Ready
- **Multi-tenancy** — One database user per tenant with isolated permissions
- **Terragrunt IaC** — DRY multi-environment deployments (dev/staging/prod)
- **Observability** — CloudWatch dashboards, X-Ray tracing, structured logging
- **Idempotency** — Request deduplication with configurable TTL

## 📊 Performance Benchmarks

| Metric | Without Optimization | With Optimization | Improvement |
|--------|---------------------|-------------------|-------------|
| First Query Latency | 500ms | 500ms | — |
| Subsequent Queries | 500ms | 100ms | **80% ⬇️** |
| Result Parsing (10K rows) | 120ms | 35ms | **71% ⬇️** |
| Cold Start | 3s | 1.5s | **50% ⬇️** |

> Optimizations include session reuse and CSV format parsing via `get_statement_result_v2`.

## 📚 Documentation

Full documentation is available at **[zhiweio.github.io/redshift-spectra](https://zhiweio.github.io/redshift-spectra/)**

| Section | Description |
|---------|-------------|
| [Getting Started](docs/getting-started/installation.md) | Installation, configuration, quickstart |
| [User Guide](docs/user-guide/query-api.md) | Query API (sync), Bulk API (async) |
| [Concepts](docs/concepts/architecture.md) | Architecture, multi-tenancy, data delivery |
| [Security](docs/security/overview.md) | Zero-trust model, authentication, SQL validation |
| [Performance](docs/performance/overview.md) | Session reuse, CSV format optimization |
| [Deployment](docs/deployment/infrastructure.md) | Terragrunt, Lambda layers, monitoring |
| [API Reference](docs/api-reference.md) | Complete REST API specification |

## 🛠️ Development

### Local Development with LocalStack

For local development and testing without AWS costs:

```bash
# Start LocalStack
task local:start

# Deploy infrastructure to LocalStack
task local:deploy

# Check status
task local:status

# Clean up
task local:stop
```

> ⚠️ **Note**: Full functionality (Redshift Data API, Lambda Layers) requires [LocalStack Pro](https://localstack.cloud/pricing/). See the [LocalStack documentation](docs/development/localstack.md) for details on Community vs Pro features.

### Running Tests

```bash
# Install dev dependencies
task setup:install-dev

# Run all tests (450+ test cases)
task test:all

# Lint and format Python code
task lint:check
task lint:format

# Format Terraform/Terragrunt files
task infra:iac-fmt

# Build Lambda packages
task build:all

# Serve documentation locally
task docs:serve
```

## 📁 Project Structure

```
redshift-spectra/
├── src/spectra/          # Lambda function source code
│   ├── handlers/         # API endpoint handlers
│   ├── services/         # Business logic (Redshift, S3, DynamoDB)
│   ├── middleware/       # Tenant context, authentication
│   ├── models/           # Request/response schemas
│   └── utils/            # SQL validator, config, helpers
├── terraform/            # Terraform modules
│   └── modules/          # api-gateway, dynamodb, iam, lambda, monitoring, s3
├── terragrunt/           # Terragrunt configurations
│   └── environments/     # local, dev, prod environments
├── tests/                # Unit and integration tests
│   ├── unit/             # Handler, service, utility tests
│   └── integration/      # End-to-end workflow tests
└── docs/                 # MkDocs documentation source
```

## 🤝 Contributing

Contributions are welcome! Please see our [Contributing Guide](docs/development/contributing.md) for details.

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>Built with ❤️ for the data engineering community</strong>
</p>
<p align="center">
  <a href="https://zhiweio.github.io/redshift-spectra/">Documentation</a> •
  <a href="https://github.com/zhiweio/redshift-spectra/issues">Report Bug</a> •
  <a href="https://github.com/zhiweio/redshift-spectra/issues">Request Feature</a>
</p>
