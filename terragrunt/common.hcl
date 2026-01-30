# =============================================================================
# Common Variables Configuration
# =============================================================================
# This file contains common variables shared across all modules.
# It's included by child terragrunt.hcl files using read_terragrunt_config.
# =============================================================================

locals {
  # -----------------------------------------------------------------------------
  # Lambda Configuration Defaults
  # -----------------------------------------------------------------------------
  lambda_defaults = {
    python_runtime = "python3.11"
    timeout        = 60
    memory_size    = 512
    log_level      = "INFO"
  }

  # -----------------------------------------------------------------------------
  # DynamoDB Configuration Defaults
  # -----------------------------------------------------------------------------
  dynamodb_defaults = {
    billing_mode   = "PAY_PER_REQUEST"
    read_capacity  = 5
    write_capacity = 5
  }

  # -----------------------------------------------------------------------------
  # API Gateway Configuration Defaults
  # -----------------------------------------------------------------------------
  api_gateway_defaults = {
    throttling_burst_limit = 100
    throttling_rate_limit  = 50
  }

  # -----------------------------------------------------------------------------
  # S3 Configuration Defaults
  # -----------------------------------------------------------------------------
  s3_defaults = {
    versioning_enabled      = false
    lifecycle_enabled       = true
    results_expiration_days = 7
    temp_expiration_days    = 1
  }

  # -----------------------------------------------------------------------------
  # Monitoring Configuration Defaults
  # -----------------------------------------------------------------------------
  monitoring_defaults = {
    log_retention_days           = 30
    enable_alerting              = false
    lambda_error_threshold       = 10
    lambda_duration_threshold_ms = 10000
    api_5xx_error_threshold      = 5
    api_latency_threshold_ms     = 5000
  }
}
