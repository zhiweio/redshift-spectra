# =============================================================================
# Region Configuration - LocalStack us-east-1
# =============================================================================
# LocalStack region configuration. LocalStack runs on localhost:4566.
# =============================================================================

locals {
  aws_region = "us-east-1"

  # LocalStack endpoint configuration
  localstack = {
    endpoint = "http://localhost:4566"
  }
}
