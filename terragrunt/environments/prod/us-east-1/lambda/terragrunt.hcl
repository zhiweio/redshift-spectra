# =============================================================================
# Lambda Module - Production
# =============================================================================

include "root" {
  path   = find_in_parent_folders()
  expose = true
}

include "common" {
  path   = find_in_parent_folders("common.hcl")
  expose = true
}

dependency "iam" {
  config_path = "../iam"
  mock_outputs = {
    authorizer_role_arn  = "arn:aws:iam::987654321098:role/mock-authorizer-role"
    api_handler_role_arn = "arn:aws:iam::987654321098:role/mock-api-role"
    worker_role_arn      = "arn:aws:iam::987654321098:role/mock-worker-role"
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

dependency "dynamodb" {
  config_path = "../dynamodb"
  mock_outputs = {
    jobs_table_name       = "mock-jobs-table"
    sessions_table_name   = "mock-sessions-table"
    bulk_jobs_table_name  = "mock-bulk-jobs-table"
    jobs_table_stream_arn = "arn:aws:dynamodb:us-east-1:987654321098:table/mock-jobs/stream/2024-01-01T00:00:00.000"
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

dependency "s3" {
  config_path = "../s3"
  mock_outputs = {
    bucket_name = "mock-bucket"
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

dependency "secrets_manager" {
  config_path = "../secrets-manager"
  mock_outputs = {
    redshift_credentials_secret_arn = "arn:aws:secretsmanager:us-east-1:987654321098:secret:mock-redshift-credentials"
    jwt_secret_arn                  = "arn:aws:secretsmanager:us-east-1:987654321098:secret:mock-jwt-secret"
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

locals {
  account_vars = read_terragrunt_config(find_in_parent_folders("account.hcl"))
  region_vars  = read_terragrunt_config(find_in_parent_folders("region.hcl"))
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))

  account = local.account_vars.locals
  region  = local.region_vars.locals
  env     = local.env_vars.locals.settings
  common  = include.common.locals

  lambda_dist_dir = "${get_repo_root()}/dist/lambda"
}

terraform {
  source = "${get_repo_root()}/terraform/modules/lambda"
}

inputs = {
  name_prefix = "${include.root.locals.project_name}-${include.root.locals.environment}"
  environment = include.root.locals.environment
  region      = local.region.aws_region
  account_id  = local.account.account_id

  # Production-optimized settings
  python_runtime     = "python3.11"
  lambda_timeout     = lookup(local.env.lambda, "timeout", 120)
  lambda_memory_size = lookup(local.env.lambda, "memory_size", 1024)
  log_level          = lookup(local.env.lambda, "log_level", "INFO")
  log_retention_days = lookup(local.env.monitoring, "log_retention_days", 90)

  # Lambda Layer
  create_layer       = true
  layer_package_path = "${local.lambda_dist_dir}/layer.zip"

  # Function packages
  authorizer_package_path = "${local.lambda_dist_dir}/authorizer.zip"
  api_package_path        = "${local.lambda_dist_dir}/api-handler.zip"
  worker_package_path     = "${local.lambda_dist_dir}/worker.zip"

  # IAM roles
  authorizer_role_arn = dependency.iam.outputs.authorizer_role_arn
  api_role_arn        = dependency.iam.outputs.api_handler_role_arn
  worker_role_arn     = dependency.iam.outputs.worker_role_arn

  # ==========================================================================
  # Redshift Configuration
  # ==========================================================================
  redshift_cluster_id                   = lookup(local.env.redshift, "cluster_id", "")
  redshift_database                     = local.env.redshift.database
  redshift_workgroup_name               = local.env.redshift.workgroup_name
  redshift_secret_arn                   = dependency.secrets_manager.outputs.redshift_credentials_secret_arn
  redshift_session_keep_alive_seconds   = lookup(local.env, "redshift_session_keep_alive_seconds", 3600)
  redshift_session_idle_timeout_seconds = lookup(local.env, "redshift_session_idle_timeout_seconds", 300)

  # ==========================================================================
  # DynamoDB Configuration
  # ==========================================================================
  dynamodb_table_name          = dependency.dynamodb.outputs.jobs_table_name
  dynamodb_sessions_table_name = dependency.dynamodb.outputs.sessions_table_name
  dynamodb_bulk_table_name     = dependency.dynamodb.outputs.bulk_jobs_table_name

  # ==========================================================================
  # S3 Configuration
  # ==========================================================================
  s3_bucket_name    = dependency.s3.outputs.bucket_name
  s3_use_path_style = false

  # ==========================================================================
  # Authentication Configuration
  # ==========================================================================
  auth_mode        = "jwt"
  jwt_secret_arn   = dependency.secrets_manager.outputs.jwt_secret_arn
  jwt_issuer       = "redshift-spectra-prod"
  jwt_audience     = "redshift-spectra-api"
  jwt_expiry_hours = lookup(local.env.security, "jwt_expiry_hours", 8)

  # ==========================================================================
  # Not LocalStack
  # ==========================================================================
  is_localstack = false

  # DynamoDB Stream trigger
  enable_dynamodb_trigger = true
  dynamodb_stream_arn     = dependency.dynamodb.outputs.jobs_table_stream_arn

  # VPC configuration (enabled for production)
  vpc_subnet_ids         = lookup(local.account.settings, "subnet_ids", [])
  vpc_security_group_ids = []

  # Reserved concurrency for production stability
  api_reserved_concurrency    = 100
  worker_reserved_concurrency = 50

  # Enable X-Ray tracing
  enable_xray = true

  tags = include.root.locals.common_tags
}
