# =============================================================================
# Environment Configuration - LocalStack (Local Development)
# =============================================================================
# This file contains environment-specific settings for LocalStack development.
# Optimized for fast iteration and debugging.
# =============================================================================

locals {
  environment = "local"

  # LocalStack-specific flag
  is_localstack = true

  # Environment-specific overrides
  settings = {
    # Redshift configuration (mocked in LocalStack)
    redshift = {
      workgroup_name = "default"
      database       = "local"
    }

    # Lambda configuration (optimized for local dev)
    lambda = {
      python_runtime = "python3.11"
      log_level      = "DEBUG"
      timeout        = 300 # Longer timeout for debugging
      memory_size    = 512
    }

    # DynamoDB configuration
    dynamodb = {
      billing_mode       = "PAY_PER_REQUEST"
      jobs_ttl_days      = 1 # Short TTL for local dev
      sessions_ttl_hours = 1
    }

    # S3 configuration
    s3 = {
      versioning_enabled      = false
      results_expiration_days = 1
    }

    # API Gateway configuration
    api_gateway = {
      throttling_burst_limit = 1000 # No throttling in local
      throttling_rate_limit  = 1000
    }

    # Monitoring configuration
    monitoring = {
      enable_alerting    = false
      log_retention_days = 1
    }

    # Security (relaxed for local development)
    security = {
      jwt_expiry_hours  = 720 # 30 days for local dev
      create_jwt_secret = true
    }

    # CORS (allow all for local development)
    cors = {
      allowed_origins = ["*"]
    }
  }
}
