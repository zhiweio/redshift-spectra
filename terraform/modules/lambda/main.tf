# =============================================================================
# Lambda Module - Serverless Functions
# =============================================================================
# Creates Lambda functions for:
# - API Handler (REST API endpoints)
# - Worker (Async job processing)
# - Authorizer (JWT/IAM authorization)
# 
# Architecture:
# - Lambda Layer: Contains all third-party dependencies (boto3, pydantic, etc.)
# - Lambda Functions: Contains only application code (spectra package)
# This separation reduces deployment size and speeds up updates.
# =============================================================================

# =============================================================================
# Lambda Layer (Shared Dependencies)
# =============================================================================
# The layer contains all pip dependencies, generated from pyproject.toml
# via `make package-layer`. Functions only contain application code.
# =============================================================================

resource "aws_lambda_layer_version" "dependencies" {
  count = var.create_layer ? 1 : 0

  layer_name               = "${var.name_prefix}-dependencies"
  description              = "Redshift Spectra shared dependencies (aws-lambda-powertools, pydantic, boto3, pyarrow)"
  compatible_runtimes      = [var.python_runtime]
  compatible_architectures = ["x86_64"]
  filename                 = var.layer_package_path
  source_code_hash         = filebase64sha256(var.layer_package_path)

  lifecycle {
    create_before_destroy = true
  }
}

# Determine which layer ARNs to use
locals {
  # Priority: 1) Newly created layer, 2) Externally provided layer ARN, 3) Empty
  layer_arns = var.create_layer ? [aws_lambda_layer_version.dependencies[0].arn] : (
    var.lambda_layer_arn != null ? [var.lambda_layer_arn] : []
  )

  # Common environment variables for all functions
  common_environment = merge(var.environment_variables, {
    # AWS Lambda Powertools configuration
    POWERTOOLS_SERVICE_NAME      = var.name_prefix
    POWERTOOLS_LOG_LEVEL         = var.log_level
    POWERTOOLS_METRICS_NAMESPACE = "${var.name_prefix}/metrics"
    
    # Application configuration
    LOG_LEVEL = var.log_level
  })
}

# =============================================================================
# CloudWatch Log Groups
# =============================================================================

resource "aws_cloudwatch_log_group" "authorizer" {
  name              = "/aws/lambda/${var.name_prefix}-authorizer"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${var.name_prefix}-api"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/aws/lambda/${var.name_prefix}-worker"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn

  tags = var.tags
}

# =============================================================================
# Authorizer Lambda Function
# =============================================================================

resource "aws_lambda_function" "authorizer" {
  function_name = "${var.name_prefix}-authorizer"
  description   = "JWT/IAM token authorizer for API Gateway"
  role          = var.authorizer_role_arn
  handler       = "spectra.handlers.authorizer.handler"
  runtime       = var.python_runtime
  timeout       = 30
  memory_size   = 256

  filename         = var.authorizer_package_path
  source_code_hash = filebase64sha256(var.authorizer_package_path)

  layers = local.layer_arns

  environment {
    variables = merge(local.common_environment, {
      JWT_SECRET_ARN   = var.jwt_secret_arn
      JWT_EXPIRY_HOURS = var.jwt_expiry_hours
      JWT_ISSUER       = var.jwt_issuer
      JWT_AUDIENCE     = var.jwt_audience
    })
  }

  vpc_config {
    subnet_ids         = var.vpc_subnet_ids
    security_group_ids = var.vpc_security_group_ids
  }

  tracing_config {
    mode = var.enable_xray ? "Active" : "PassThrough"
  }

  reserved_concurrent_executions = var.authorizer_reserved_concurrency

  depends_on = [aws_cloudwatch_log_group.authorizer]

  tags = var.tags
}

# =============================================================================
# API Handler Lambda Function
# =============================================================================

resource "aws_lambda_function" "api" {
  function_name = "${var.name_prefix}-api"
  description   = "REST API handler for Redshift Spectra"
  role          = var.api_role_arn
  handler       = "spectra.handlers.api.handler"
  runtime       = var.python_runtime
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_size

  filename         = var.api_package_path
  source_code_hash = filebase64sha256(var.api_package_path)

  layers = local.layer_arns

  environment {
    variables = local.common_environment
  }

  vpc_config {
    subnet_ids         = var.vpc_subnet_ids
    security_group_ids = var.vpc_security_group_ids
  }

  tracing_config {
    mode = var.enable_xray ? "Active" : "PassThrough"
  }

  reserved_concurrent_executions = var.api_reserved_concurrency

  depends_on = [aws_cloudwatch_log_group.api]

  tags = var.tags
}

# =============================================================================
# Worker Lambda Function
# =============================================================================

resource "aws_lambda_function" "worker" {
  function_name = "${var.name_prefix}-worker"
  description   = "Async job processor for bulk operations and long-running queries"
  role          = var.worker_role_arn
  handler       = "spectra.handlers.worker.handler"
  runtime       = var.python_runtime
  timeout       = var.worker_timeout
  memory_size   = var.worker_memory_size

  filename         = var.worker_package_path
  source_code_hash = filebase64sha256(var.worker_package_path)

  layers = local.layer_arns

  environment {
    variables = merge(local.common_environment, {
      BULK_PROCESSING_ENABLED = tostring(var.enable_bulk_processing)
      MAX_BATCH_SIZE          = tostring(var.max_batch_size)
    })
  }

  vpc_config {
    subnet_ids         = var.vpc_subnet_ids
    security_group_ids = var.vpc_security_group_ids
  }

  tracing_config {
    mode = var.enable_xray ? "Active" : "PassThrough"
  }

  reserved_concurrent_executions = var.worker_reserved_concurrency

  depends_on = [aws_cloudwatch_log_group.worker]

  tags = var.tags
}

# =============================================================================
# Lambda Permissions for API Gateway
# =============================================================================

resource "aws_lambda_permission" "api_gateway_authorizer" {
  statement_id  = "AllowAPIGatewayInvokeAuthorizer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.authorizer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.api_gateway_execution_arn}/*/*"
}

resource "aws_lambda_permission" "api_gateway_api" {
  statement_id  = "AllowAPIGatewayInvokeAPI"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.api_gateway_execution_arn}/*/*"
}

# =============================================================================
# Event Source Mappings (for Worker)
# =============================================================================

resource "aws_lambda_event_source_mapping" "dynamodb_trigger" {
  count = var.enable_dynamodb_trigger ? 1 : 0

  event_source_arn  = var.dynamodb_stream_arn
  function_name     = aws_lambda_function.worker.arn
  starting_position = "LATEST"

  batch_size                         = var.dynamodb_batch_size
  maximum_batching_window_in_seconds = var.dynamodb_batch_window

  filter_criteria {
    filter {
      pattern = jsonencode({
        eventName = ["INSERT", "MODIFY"]
        dynamodb = {
          NewImage = {
            status = {
              S = ["PENDING", "UPLOAD_COMPLETE"]
            }
          }
        }
      })
    }
  }

  destination_config {
    on_failure {
      destination_arn = var.dlq_arn
    }
  }

  function_response_types = ["ReportBatchItemFailures"]
}

# =============================================================================
# Async Invocation Configuration
# =============================================================================

resource "aws_lambda_function_event_invoke_config" "worker" {
  function_name                = aws_lambda_function.worker.function_name
  maximum_event_age_in_seconds = 3600
  maximum_retry_attempts       = 2

  dynamic "destination_config" {
    for_each = var.dlq_arn != null ? [1] : []
    content {
      on_failure {
        destination = var.dlq_arn
      }
    }
  }
}
