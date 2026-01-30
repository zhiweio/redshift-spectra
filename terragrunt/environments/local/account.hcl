# =============================================================================
# Account Configuration - LocalStack (Local Development)
# =============================================================================
# This file contains account-specific settings for the LocalStack local
# development environment. Uses fake AWS account ID for LocalStack.
# =============================================================================

locals {
  account_id   = "000000000000"  # LocalStack default account ID
  account_name = "localstack"
  
  # Account-level settings
  settings = {
    # VPC settings (not used in LocalStack)
    vpc_enabled = false
    vpc_id      = null
    subnet_ids  = []
    
    # KMS settings (not used in LocalStack)
    use_custom_kms_key = false
    kms_key_arn        = null
  }
}
