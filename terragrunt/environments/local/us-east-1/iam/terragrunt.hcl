# =============================================================================
# IAM Module - Terragrunt Configuration (LocalStack)
# =============================================================================
# This module creates IAM roles and policies in LocalStack for local development.
# Note: LocalStack IAM is permissive by default, but we still create roles
# to maintain consistency with production configuration.
# =============================================================================

# Include the LocalStack root terragrunt.hcl configuration
include "root" {
  path = find_in_parent_folders("terragrunt-local.hcl")
}

# Include common variables
include "common" {
  path   = find_in_parent_folders("common.hcl")
  expose = true
}

# Dependencies
dependency "dynamodb" {
  config_path = "../dynamodb"
  
  mock_outputs = {
    jobs_table_arn       = "arn:aws:dynamodb:us-east-1:000000000000:table/mock-jobs"
    sessions_table_arn   = "arn:aws:dynamodb:us-east-1:000000000000:table/mock-sessions"
    jobs_table_name      = "mock-jobs"
    sessions_table_name  = "mock-sessions"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

dependency "s3" {
  config_path = "../s3"
  
  mock_outputs = {
    bucket_arn  = "arn:aws:s3:::mock-bucket"
    bucket_name = "mock-bucket"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

# Load configuration
locals {
  account_vars = read_terragrunt_config(find_in_parent_folders("account.hcl"))
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  
  account = local.account_vars.locals
  env     = local.env_vars.locals.settings
}

# Terraform module source
terraform {
  source = "${get_repo_root()}/terraform/modules/iam"
}

# Module inputs
inputs = {
  name_prefix = "${include.root.locals.project_name}-${include.root.locals.environment}"
  
  # DynamoDB permissions
  dynamodb_table_arns = [
    dependency.dynamodb.outputs.jobs_table_arn,
    dependency.dynamodb.outputs.sessions_table_arn
  ]
  
  # S3 permissions
  s3_bucket_arn = dependency.s3.outputs.bucket_arn
  
  # LocalStack doesn't require Redshift permissions (mocked)
  redshift_workgroup_arn = "arn:aws:redshift-serverless:us-east-1:000000000000:workgroup/*"
  redshift_namespace_arn = "arn:aws:redshift-serverless:us-east-1:000000000000:namespace/*"
  
  # Secrets Manager (LocalStack)
  secrets_arn_prefix = "arn:aws:secretsmanager:us-east-1:000000000000:secret:${include.root.locals.project_name}/${include.root.locals.environment}/*"
  
  # No KMS in LocalStack
  kms_key_arn = null
  
  # No VPC in LocalStack
  enable_vpc = false
}
