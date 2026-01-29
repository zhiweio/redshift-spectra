# =============================================================================
# Account Configuration - Production
# =============================================================================
# This file contains account-specific settings for the production AWS account.
# =============================================================================

locals {
  account_id   = "987654321098"  # Replace with your production AWS account ID
  account_name = "production"
  
  # Account-level settings
  settings = {
    # VPC settings (recommended for production)
    vpc_enabled = true
    vpc_id      = "vpc-xxxxxxxxx"  # Replace with your VPC ID
    subnet_ids  = [
      "subnet-aaaaaaa",  # Replace with your subnet IDs
      "subnet-bbbbbbb",
    ]
    
    # KMS settings (recommended for production)
    use_custom_kms_key = true
    kms_key_arn        = "arn:aws:kms:us-east-1:987654321098:key/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  }
}
