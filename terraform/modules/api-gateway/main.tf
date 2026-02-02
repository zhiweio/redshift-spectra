# =============================================================================
# API Gateway Module
# RESTful API for Redshift Spectra DaaS Platform
# =============================================================================

# -----------------------------------------------------------------------------
# REST API Definition
# -----------------------------------------------------------------------------
resource "aws_api_gateway_rest_api" "main" {
  name        = "${var.project_name}-${var.environment}-api"
  description = "Redshift Spectra DaaS API - ${var.environment}"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-api"
  })
}

# -----------------------------------------------------------------------------
# API Gateway Authorizer (Lambda or IAM)
# -----------------------------------------------------------------------------
resource "aws_api_gateway_authorizer" "lambda" {
  count                            = var.enable_lambda_authorizer ? 1 : 0
  name                             = "${var.project_name}-authorizer"
  rest_api_id                      = aws_api_gateway_rest_api.main.id
  authorizer_uri                   = var.authorizer_lambda_invoke_arn
  authorizer_credentials           = var.authorizer_role_arn
  type                             = "REQUEST"
  identity_source                  = "method.request.header.Authorization"
  authorizer_result_ttl_in_seconds = var.authorizer_cache_ttl
}

# -----------------------------------------------------------------------------
# /v1 Resource
# -----------------------------------------------------------------------------
resource "aws_api_gateway_resource" "v1" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "v1"
}

# -----------------------------------------------------------------------------
# /v1/query Resource & Methods
# -----------------------------------------------------------------------------
resource "aws_api_gateway_resource" "query" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.v1.id
  path_part   = "query"
}

resource "aws_api_gateway_method" "query_post" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.query.id
  http_method   = "POST"
  authorization = var.enable_lambda_authorizer ? "CUSTOM" : "AWS_IAM"
  authorizer_id = var.enable_lambda_authorizer ? aws_api_gateway_authorizer.lambda[0].id : null

  request_parameters = {
    "method.request.header.X-Tenant-Id" = true
  }
}

resource "aws_api_gateway_integration" "query_post" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.query.id
  http_method             = aws_api_gateway_method.query_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.query_lambda_invoke_arn
}

# -----------------------------------------------------------------------------
# /v1/jobs Resource & Methods
# -----------------------------------------------------------------------------
resource "aws_api_gateway_resource" "jobs" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.v1.id
  path_part   = "jobs"
}

resource "aws_api_gateway_resource" "job_id" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.jobs.id
  path_part   = "{jobId}"
}

resource "aws_api_gateway_method" "job_get" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.job_id.id
  http_method   = "GET"
  authorization = var.enable_lambda_authorizer ? "CUSTOM" : "AWS_IAM"
  authorizer_id = var.enable_lambda_authorizer ? aws_api_gateway_authorizer.lambda[0].id : null

  request_parameters = {
    "method.request.path.jobId"         = true
    "method.request.header.X-Tenant-Id" = true
  }
}

resource "aws_api_gateway_integration" "job_get" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.job_id.id
  http_method             = aws_api_gateway_method.job_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.status_lambda_invoke_arn
}

# -----------------------------------------------------------------------------
# /v1/jobs/{jobId}/result Resource & Methods
# -----------------------------------------------------------------------------
resource "aws_api_gateway_resource" "job_result" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.job_id.id
  path_part   = "result"
}

resource "aws_api_gateway_method" "result_get" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.job_result.id
  http_method   = "GET"
  authorization = var.enable_lambda_authorizer ? "CUSTOM" : "AWS_IAM"
  authorizer_id = var.enable_lambda_authorizer ? aws_api_gateway_authorizer.lambda[0].id : null

  request_parameters = {
    "method.request.path.jobId"         = true
    "method.request.header.X-Tenant-Id" = true
  }
}

resource "aws_api_gateway_integration" "result_get" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.job_result.id
  http_method             = aws_api_gateway_method.result_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.result_lambda_invoke_arn
}

# -----------------------------------------------------------------------------
# /v1/bulk Resource & Methods (Salesforce Bulk v2 Style)
# -----------------------------------------------------------------------------
resource "aws_api_gateway_resource" "bulk" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.v1.id
  path_part   = "bulk"
}

# POST /v1/bulk - Create bulk job
resource "aws_api_gateway_method" "bulk_post" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.bulk.id
  http_method   = "POST"
  authorization = var.enable_lambda_authorizer ? "CUSTOM" : "AWS_IAM"
  authorizer_id = var.enable_lambda_authorizer ? aws_api_gateway_authorizer.lambda[0].id : null

  request_parameters = {
    "method.request.header.X-Tenant-Id" = true
  }
}

resource "aws_api_gateway_integration" "bulk_post" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.bulk.id
  http_method             = aws_api_gateway_method.bulk_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.bulk_lambda_invoke_arn
}

# /v1/bulk/{jobId}
resource "aws_api_gateway_resource" "bulk_job_id" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.bulk.id
  path_part   = "{jobId}"
}

# GET /v1/bulk/{jobId} - Get bulk job status
resource "aws_api_gateway_method" "bulk_job_get" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.bulk_job_id.id
  http_method   = "GET"
  authorization = var.enable_lambda_authorizer ? "CUSTOM" : "AWS_IAM"
  authorizer_id = var.enable_lambda_authorizer ? aws_api_gateway_authorizer.lambda[0].id : null

  request_parameters = {
    "method.request.path.jobId"         = true
    "method.request.header.X-Tenant-Id" = true
  }
}

resource "aws_api_gateway_integration" "bulk_job_get" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.bulk_job_id.id
  http_method             = aws_api_gateway_method.bulk_job_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.bulk_lambda_invoke_arn
}

# PATCH /v1/bulk/{jobId} - Update bulk job state
resource "aws_api_gateway_method" "bulk_job_patch" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.bulk_job_id.id
  http_method   = "PATCH"
  authorization = var.enable_lambda_authorizer ? "CUSTOM" : "AWS_IAM"
  authorizer_id = var.enable_lambda_authorizer ? aws_api_gateway_authorizer.lambda[0].id : null

  request_parameters = {
    "method.request.path.jobId"         = true
    "method.request.header.X-Tenant-Id" = true
  }
}

resource "aws_api_gateway_integration" "bulk_job_patch" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.bulk_job_id.id
  http_method             = aws_api_gateway_method.bulk_job_patch.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.bulk_lambda_invoke_arn
}

# DELETE /v1/bulk/{jobId} - Abort bulk job
resource "aws_api_gateway_method" "bulk_job_delete" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.bulk_job_id.id
  http_method   = "DELETE"
  authorization = var.enable_lambda_authorizer ? "CUSTOM" : "AWS_IAM"
  authorizer_id = var.enable_lambda_authorizer ? aws_api_gateway_authorizer.lambda[0].id : null

  request_parameters = {
    "method.request.path.jobId"         = true
    "method.request.header.X-Tenant-Id" = true
  }
}

resource "aws_api_gateway_integration" "bulk_job_delete" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.bulk_job_id.id
  http_method             = aws_api_gateway_method.bulk_job_delete.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.bulk_lambda_invoke_arn
}

# /v1/bulk/{jobId}/batches - Upload data batches
resource "aws_api_gateway_resource" "bulk_batches" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.bulk_job_id.id
  path_part   = "batches"
}

# PUT /v1/bulk/{jobId}/batches - Upload batch data
resource "aws_api_gateway_method" "bulk_batches_put" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.bulk_batches.id
  http_method   = "PUT"
  authorization = var.enable_lambda_authorizer ? "CUSTOM" : "AWS_IAM"
  authorizer_id = var.enable_lambda_authorizer ? aws_api_gateway_authorizer.lambda[0].id : null

  request_parameters = {
    "method.request.path.jobId"          = true
    "method.request.header.X-Tenant-Id"  = true
    "method.request.header.Content-Type" = true
  }
}

resource "aws_api_gateway_integration" "bulk_batches_put" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.bulk_batches.id
  http_method             = aws_api_gateway_method.bulk_batches_put.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.bulk_lambda_invoke_arn
}

# /v1/bulk/{jobId}/results - Get export results
resource "aws_api_gateway_resource" "bulk_results" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.bulk_job_id.id
  path_part   = "results"
}

# GET /v1/bulk/{jobId}/results - Get bulk job results
resource "aws_api_gateway_method" "bulk_results_get" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.bulk_results.id
  http_method   = "GET"
  authorization = var.enable_lambda_authorizer ? "CUSTOM" : "AWS_IAM"
  authorizer_id = var.enable_lambda_authorizer ? aws_api_gateway_authorizer.lambda[0].id : null

  request_parameters = {
    "method.request.path.jobId"         = true
    "method.request.header.X-Tenant-Id" = true
  }
}

resource "aws_api_gateway_integration" "bulk_results_get" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.bulk_results.id
  http_method             = aws_api_gateway_method.bulk_results_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.bulk_lambda_invoke_arn
}

# -----------------------------------------------------------------------------
# API Gateway Deployment & Stage
# -----------------------------------------------------------------------------
resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.main.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.v1.id,
      aws_api_gateway_resource.query.id,
      aws_api_gateway_resource.jobs.id,
      aws_api_gateway_resource.bulk.id,
      aws_api_gateway_method.query_post.id,
      aws_api_gateway_method.job_get.id,
      aws_api_gateway_method.result_get.id,
      aws_api_gateway_method.bulk_post.id,
      aws_api_gateway_method.bulk_job_get.id,
      aws_api_gateway_method.bulk_job_patch.id,
      aws_api_gateway_method.bulk_batches_put.id,
      aws_api_gateway_method.bulk_results_get.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_integration.query_post,
    aws_api_gateway_integration.job_get,
    aws_api_gateway_integration.result_get,
    aws_api_gateway_integration.bulk_post,
    aws_api_gateway_integration.bulk_job_get,
    aws_api_gateway_integration.bulk_job_patch,
    aws_api_gateway_integration.bulk_batches_put,
    aws_api_gateway_integration.bulk_results_get,
  ]
}

resource "aws_api_gateway_stage" "main" {
  deployment_id = aws_api_gateway_deployment.main.id
  rest_api_id   = aws_api_gateway_rest_api.main.id
  stage_name    = var.environment

  access_log_settings {
    destination_arn = var.access_log_group_arn
    format = jsonencode({
      requestId         = "$context.requestId"
      ip                = "$context.identity.sourceIp"
      caller            = "$context.identity.caller"
      user              = "$context.identity.user"
      requestTime       = "$context.requestTime"
      httpMethod        = "$context.httpMethod"
      resourcePath      = "$context.resourcePath"
      status            = "$context.status"
      protocol          = "$context.protocol"
      responseLength    = "$context.responseLength"
      integrationStatus = "$context.integrationStatus"
      tenantId          = "$context.authorizer.tenantId"
    })
  }

  xray_tracing_enabled = var.enable_xray_tracing

  variables = {
    environment = var.environment
  }

  tags = var.tags
}

# -----------------------------------------------------------------------------
# API Gateway Method Settings (Throttling, Caching)
# -----------------------------------------------------------------------------
resource "aws_api_gateway_method_settings" "all" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  stage_name  = aws_api_gateway_stage.main.stage_name
  method_path = "*/*"

  settings {
    metrics_enabled        = true
    logging_level          = var.logging_level
    data_trace_enabled     = var.environment != "prod"
    throttling_burst_limit = var.throttling_burst_limit
    throttling_rate_limit  = var.throttling_rate_limit
    caching_enabled        = var.enable_caching
    cache_ttl_in_seconds   = var.cache_ttl
  }
}

# -----------------------------------------------------------------------------
# Lambda Permissions for API Gateway
# -----------------------------------------------------------------------------
resource "aws_lambda_permission" "query" {
  statement_id  = "AllowAPIGatewayInvoke-Query"
  action        = "lambda:InvokeFunction"
  function_name = var.query_lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

resource "aws_lambda_permission" "status" {
  statement_id  = "AllowAPIGatewayInvoke-Status"
  action        = "lambda:InvokeFunction"
  function_name = var.status_lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

resource "aws_lambda_permission" "result" {
  statement_id  = "AllowAPIGatewayInvoke-Result"
  action        = "lambda:InvokeFunction"
  function_name = var.result_lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

resource "aws_lambda_permission" "bulk" {
  statement_id  = "AllowAPIGatewayInvoke-Bulk"
  action        = "lambda:InvokeFunction"
  function_name = var.bulk_lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

# -----------------------------------------------------------------------------
# WAF Integration (Optional)
# -----------------------------------------------------------------------------
resource "aws_wafv2_web_acl_association" "main" {
  count        = var.waf_acl_arn != null ? 1 : 0
  resource_arn = aws_api_gateway_stage.main.arn
  web_acl_arn  = var.waf_acl_arn
}

# -----------------------------------------------------------------------------
# Custom Domain (Optional)
# -----------------------------------------------------------------------------
resource "aws_api_gateway_domain_name" "main" {
  count                    = var.custom_domain_name != null ? 1 : 0
  domain_name              = var.custom_domain_name
  regional_certificate_arn = var.certificate_arn

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = var.tags
}

resource "aws_api_gateway_base_path_mapping" "main" {
  count       = var.custom_domain_name != null ? 1 : 0
  api_id      = aws_api_gateway_rest_api.main.id
  stage_name  = aws_api_gateway_stage.main.stage_name
  domain_name = aws_api_gateway_domain_name.main[0].domain_name
  base_path   = var.base_path
}
