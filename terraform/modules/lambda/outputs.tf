# =============================================================================
# Lambda Module - Outputs
# =============================================================================

output "authorizer_function_name" {
  description = "Name of the authorizer Lambda function"
  value       = aws_lambda_function.authorizer.function_name
}

output "authorizer_function_arn" {
  description = "ARN of the authorizer Lambda function"
  value       = aws_lambda_function.authorizer.arn
}

output "authorizer_invoke_arn" {
  description = "Invoke ARN of the authorizer Lambda function"
  value       = aws_lambda_function.authorizer.invoke_arn
}

output "api_function_name" {
  description = "Name of the API handler Lambda function"
  value       = aws_lambda_function.api.function_name
}

output "api_function_arn" {
  description = "ARN of the API handler Lambda function"
  value       = aws_lambda_function.api.arn
}

output "api_invoke_arn" {
  description = "Invoke ARN of the API handler Lambda function"
  value       = aws_lambda_function.api.invoke_arn
}

output "worker_function_name" {
  description = "Name of the worker Lambda function"
  value       = aws_lambda_function.worker.function_name
}

output "worker_function_arn" {
  description = "ARN of the worker Lambda function"
  value       = aws_lambda_function.worker.arn
}

output "worker_invoke_arn" {
  description = "Invoke ARN of the worker Lambda function"
  value       = aws_lambda_function.worker.invoke_arn
}

output "layer_arn" {
  description = "ARN of the Lambda layer (if created)"
  value       = var.create_layer ? aws_lambda_layer_version.dependencies[0].arn : null
}

output "log_group_arns" {
  description = "ARNs of CloudWatch log groups"
  value = {
    authorizer = aws_cloudwatch_log_group.authorizer.arn
    api        = aws_cloudwatch_log_group.api.arn
    worker     = aws_cloudwatch_log_group.worker.arn
  }
}
