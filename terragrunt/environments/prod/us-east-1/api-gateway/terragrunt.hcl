# =============================================================================
# API Gateway Module - Production
# =============================================================================

include "root" {
  path = find_in_parent_folders()
}

include "common" {
  path   = find_in_parent_folders("common.hcl")
  expose = true
}

dependency "lambda" {
  config_path = "../lambda"
  mock_outputs = {
    api_function_name     = "mock-api-function"
    api_invoke_arn        = "arn:aws:lambda:us-east-1:987654321098:function:mock-api"
    authorizer_invoke_arn = "arn:aws:lambda:us-east-1:987654321098:function:mock-authorizer"
    log_group_arns        = { api = "arn:aws:logs:us-east-1:987654321098:log-group:/aws/lambda/mock-api" }
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

dependency "monitoring" {
  config_path = "../monitoring"
  mock_outputs = {
    api_gateway_log_group_arn = "arn:aws:logs:us-east-1:987654321098:log-group:/aws/api-gateway/mock"
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan"]
}

locals {
  env_vars = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  env      = local.env_vars.locals.settings
  common   = include.common.locals
}

terraform {
  source = "${get_repo_root()}/terraform/modules/api-gateway"
}

inputs = {
  project_name = include.root.locals.project_name
  environment  = include.root.locals.environment

  # Lambda integrations
  query_lambda_invoke_arn     = dependency.lambda.outputs.api_invoke_arn
  query_lambda_function_name  = dependency.lambda.outputs.api_function_name
  status_lambda_invoke_arn    = dependency.lambda.outputs.api_invoke_arn
  status_lambda_function_name = dependency.lambda.outputs.api_function_name
  result_lambda_invoke_arn    = dependency.lambda.outputs.api_invoke_arn
  result_lambda_function_name = dependency.lambda.outputs.api_function_name
  bulk_lambda_invoke_arn      = dependency.lambda.outputs.api_invoke_arn
  bulk_lambda_function_name   = dependency.lambda.outputs.api_function_name

  # Authorization
  enable_lambda_authorizer     = true
  authorizer_lambda_invoke_arn = dependency.lambda.outputs.authorizer_invoke_arn
  authorizer_cache_ttl         = 300

  # Logging
  access_log_group_arn = dependency.monitoring.outputs.api_gateway_log_group_arn
  logging_level        = "INFO"

  # Higher throttling limits for production
  throttling_burst_limit = lookup(local.env.api_gateway, "throttling_burst_limit", 500)
  throttling_rate_limit  = lookup(local.env.api_gateway, "throttling_rate_limit", 200)

  # Enable WAF for production (if configured)
  # waf_acl_arn = "arn:aws:wafv2:..."
}
