# =============================================================================
# Account Configuration - Development
# =============================================================================
# This file contains account-specific settings for the development AWS account.
# =============================================================================

locals {
  account_id   = "123456789012" # Replace with your dev AWS account ID
  account_name = "development"

  # Account-level settings
  settings = {
    # VPC settings (if using VPC for Lambda)
    vpc_enabled = false
    vpc_id      = null
    subnet_ids  = []

    # KMS settings
    use_custom_kms_key = false
    kms_key_arn        = null
  }
}
