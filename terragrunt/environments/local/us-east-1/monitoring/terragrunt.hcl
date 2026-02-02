# =============================================================================
# Monitoring Module - Terragrunt Configuration (LocalStack)
# =============================================================================
# This module creates CloudWatch log groups and basic monitoring in LocalStack.
# Note: LocalStack has limited CloudWatch support, but log groups work.
# Dashboards and alarms may have limited functionality.
# =============================================================================

# Include the LocalStack root terragrunt.hcl configuration
include "root" {
  path   = find_in_parent_folders("terragrunt-local.hcl")
  expose = true
}

# Include common variables
include "common" {
  path   = find_in_parent_folders("common.hcl")
  expose = true
}

# Dependencies - Lambda must be created first for function names
dependency "lambda" {
  config_path = "../lambda"

  mock_outputs = {
    api_function_name        = "mock-api-function"
    worker_function_name     = "mock-worker-function"
    authorizer_function_name = "mock-authorizer-function"
    log_group_arns = {
      api        = "arn:aws:logs:us-east-1:000000000000:log-group:/aws/lambda/mock-api"
      worker     = "arn:aws:logs:us-east-1:000000000000:log-group:/aws/lambda/mock-worker"
      authorizer = "arn:aws:logs:us-east-1:000000000000:log-group:/aws/lambda/mock-authorizer"
    }
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

# Load configuration
locals {
  region_vars = read_terragrunt_config(find_in_parent_folders("region.hcl"))
  env_vars    = read_terragrunt_config(find_in_parent_folders("env.hcl"))

  region = local.region_vars.locals
  env    = local.env_vars.locals.settings

  common = include.common.locals
}

# Terraform module source
terraform {
  source = "${get_repo_root()}/terraform/modules/monitoring"
}

# Module inputs
inputs = {
  project_name = include.root.locals.project_name
  environment  = include.root.locals.environment
  aws_region   = local.region.aws_region

  # Short log retention for local dev
  log_retention_days = lookup(local.env.monitoring, "log_retention_days", 1)

  # Lambda function names (from Lambda module outputs)
  lambda_function_names = {
    api        = dependency.lambda.outputs.api_function_name
    worker     = dependency.lambda.outputs.worker_function_name
    authorizer = dependency.lambda.outputs.authorizer_function_name
  }

  # Disable CloudWatch Insights Queries in LocalStack (not supported)
  # Setting to null will skip creating query definitions
  lambda_log_group_names = null

  # Relaxed alarm thresholds for local development
  lambda_error_threshold       = 100    # High threshold (essentially disabled)
  lambda_duration_threshold_ms = 300000 # 5 minutes (very high for local debugging)
  api_error_threshold          = 100
  api_latency_threshold_ms     = 60000 # 1 minute

  # No SNS alerting in LocalStack
  create_sns_topic = false
  alert_email      = null

  # No alarm actions in LocalStack
  alarm_actions = []
  ok_actions    = []

  # Disable X-Ray tracing in LocalStack (limited support)
  enable_xray_tracing = false
}
