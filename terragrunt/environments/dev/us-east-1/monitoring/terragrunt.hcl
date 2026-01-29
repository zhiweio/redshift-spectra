# =============================================================================
# Monitoring Module - Terragrunt Configuration
# =============================================================================
# This module creates CloudWatch dashboards, alarms, and log groups.
# Note: Monitoring must be deployed AFTER Lambda to get function names.
# API Gateway log group is created by this module.
# =============================================================================

# Include the root terragrunt.hcl configuration
include "root" {
  path = find_in_parent_folders()
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
      api        = "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/mock-api"
      worker     = "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/mock-worker"
      authorizer = "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/mock-authorizer"
    }
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
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
  
  # Log retention
  log_retention_days = lookup(local.env.monitoring, "log_retention_days", local.common.monitoring_defaults.log_retention_days)
  
  # Lambda function names (from Lambda module outputs)
  lambda_function_names = {
    api        = dependency.lambda.outputs.api_function_name
    worker     = dependency.lambda.outputs.worker_function_name
    authorizer = dependency.lambda.outputs.authorizer_function_name
  }
  
  # Lambda log group names for CloudWatch Insights
  lambda_log_group_names = {
    api        = "/aws/lambda/${dependency.lambda.outputs.api_function_name}"
    worker     = "/aws/lambda/${dependency.lambda.outputs.worker_function_name}"
    authorizer = "/aws/lambda/${dependency.lambda.outputs.authorizer_function_name}"
  }
  
  # Alarm thresholds
  lambda_error_threshold       = lookup(local.env.monitoring, "lambda_error_threshold", local.common.monitoring_defaults.lambda_error_threshold)
  lambda_duration_threshold_ms = lookup(local.env.monitoring, "lambda_duration_threshold_ms", local.common.monitoring_defaults.lambda_duration_threshold_ms)
  api_error_threshold          = lookup(local.env.monitoring, "api_5xx_error_threshold", local.common.monitoring_defaults.api_5xx_error_threshold)
  api_latency_threshold_ms     = lookup(local.env.monitoring, "api_latency_threshold_ms", local.common.monitoring_defaults.api_latency_threshold_ms)
  
  # SNS alerting
  create_sns_topic = lookup(local.env.monitoring, "enable_alerting", local.common.monitoring_defaults.enable_alerting)
  alert_email      = lookup(local.env.monitoring, "alert_email", null)
  
  # X-Ray tracing
  enable_xray_tracing = true
}
