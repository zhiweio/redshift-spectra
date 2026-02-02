# =============================================================================
# Environment Configuration - Development
# =============================================================================
# This file contains environment-specific settings for dev.
# =============================================================================

locals {
  environment = "dev"

  # Environment-specific overrides
  settings = {
    # Redshift configuration
    redshift = {
      workgroup_name = "default"
      database       = "dev"
    }

    # Lambda configuration (override defaults for dev)
    lambda = {
      log_level   = "DEBUG"
      timeout     = 60
      memory_size = 512
    }

    # DynamoDB configuration
    dynamodb = {
      jobs_ttl_days      = 7
      sessions_ttl_hours = 24
    }

    # S3 configuration
    s3 = {
      versioning_enabled      = false
      results_expiration_days = 7
    }

    # API Gateway configuration
    api_gateway = {
      throttling_burst_limit = 100
      throttling_rate_limit  = 50
    }

    # Monitoring configuration
    monitoring = {
      enable_alerting    = false
      log_retention_days = 7
    }

    # Security
    security = {
      jwt_expiry_hours  = 24
      create_jwt_secret = true
    }

    # CORS
    cors = {
      allowed_origins = ["*"]
    }
  }
}
