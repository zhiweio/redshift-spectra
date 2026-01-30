# =============================================================================
# Environment Configuration - Production
# =============================================================================
# This file contains environment-specific settings for production.
# =============================================================================

locals {
  environment = "prod"

  # Environment-specific overrides
  settings = {
    # Redshift configuration
    redshift = {
      workgroup_name = "production"
      database       = "analytics"
    }

    # Lambda configuration (production-optimized)
    lambda = {
      log_level   = "INFO"
      timeout     = 120
      memory_size = 1024
    }

    # DynamoDB configuration
    dynamodb = {
      billing_mode       = "PAY_PER_REQUEST"
      jobs_ttl_days      = 30
      sessions_ttl_hours = 8
    }

    # S3 configuration
    s3 = {
      versioning_enabled      = true
      results_expiration_days = 30
      temp_expiration_days    = 1
    }

    # API Gateway configuration (higher limits for production)
    api_gateway = {
      throttling_burst_limit = 500
      throttling_rate_limit  = 200
    }

    # Monitoring configuration (enable alerting in production)
    monitoring = {
      enable_alerting              = true
      log_retention_days           = 90
      alert_email                  = "ops@example.com"
      lambda_error_threshold       = 3
      lambda_duration_threshold_ms = 10000
      api_5xx_error_threshold      = 3
      api_latency_threshold_ms     = 5000
    }

    # Security (stricter settings for production)
    security = {
      jwt_expiry_hours  = 8
      create_jwt_secret = true
    }

    # CORS (restrict in production)
    cors = {
      allowed_origins = [
        "https://app.example.com",
        "https://dashboard.example.com",
      ]
    }
  }
}
