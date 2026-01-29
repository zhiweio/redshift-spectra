# Installation

This guide covers the installation of Redshift Spectra for both development and production environments.

## Prerequisites

Before installing Redshift Spectra, ensure you have:

| Requirement | Version | Purpose |
|-------------|---------|---------|
| Python | 3.11+ | Runtime environment |
| uv | Latest | Package management |
| AWS CLI | 2.x | AWS credential management |
| Terraform | >= 1.5 | Infrastructure as Code |
| Terragrunt | >= 0.50 | DRY Terraform configuration |
| Docker | Latest | Lambda layer building (optional) |

You'll also need:

- An AWS account with appropriate permissions
- An existing Amazon Redshift cluster or Redshift Serverless workgroup

## Installation Methods

### Development Setup

Clone the repository and install dependencies:

```bash
# Clone the repository
git clone https://github.com/zhiweio/redshift-spectra.git
cd redshift-spectra

# Install all dependencies (including dev tools)
make install-dev

# Verify installation
make test
```

### Production Setup

For production deployments, install only runtime dependencies:

```bash
# Install production dependencies only
make install

# Build Lambda packages
make package-all
```

## AWS Credentials

Configure AWS credentials with sufficient permissions:

```bash
# Configure AWS CLI
aws configure

# Or use environment variables
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1
```

### Required IAM Permissions

Your AWS credentials need permissions for:

- Lambda (create, update, invoke)
- API Gateway (create, manage)
- DynamoDB (create tables, read/write)
- S3 (create bucket, read/write)
- Secrets Manager (read secrets)
- Redshift Data API (execute statements)
- CloudWatch (logs, metrics)
- IAM (create roles, policies)

!!! tip "Use Least Privilege"
    For production, create a dedicated IAM user/role with only the permissions needed. See [Security Best Practices](../security/overview.md).

## Environment Configuration

Create a `.env` file from the template:

```bash
cp .env.template .env
```

Edit the `.env` file with your configuration:

```bash
# Required settings
SPECTRA_REDSHIFT_CLUSTER_ID=my-redshift-cluster
SPECTRA_REDSHIFT_DATABASE=mydb
SPECTRA_REDSHIFT_SECRET_ARN=arn:aws:secretsmanager:...
SPECTRA_S3_BUCKET_NAME=my-spectra-bucket

# Optional settings (with defaults)
SPECTRA_AWS_REGION=us-east-1
SPECTRA_LOG_LEVEL=INFO
```

See [Configuration Reference](configuration.md) for all available options.

## Verify Installation

Run the test suite to verify everything is working:

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run linting
make lint
```

## Next Steps

- [Quick Start](quickstart.md) - Deploy your first API
- [Configuration](configuration.md) - Detailed configuration options
- [Architecture](../concepts/architecture.md) - Understand how it works
