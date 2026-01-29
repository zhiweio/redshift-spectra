# =============================================================================
# Monitoring Module Outputs
# =============================================================================
# Note: Lambda log groups are managed by the Lambda module.
# This module exports API Gateway log group and monitoring resources.
# =============================================================================

# -----------------------------------------------------------------------------
# Log Groups (API Gateway)
# -----------------------------------------------------------------------------
output "api_gateway_log_group_arn" {
  description = "ARN of API Gateway log group"
  value       = aws_cloudwatch_log_group.api_gateway.arn
}

output "api_gateway_log_group_name" {
  description = "Name of API Gateway log group"
  value       = aws_cloudwatch_log_group.api_gateway.name
}

# -----------------------------------------------------------------------------
# Dashboard
# -----------------------------------------------------------------------------
output "dashboard_name" {
  description = "Name of CloudWatch dashboard"
  value       = aws_cloudwatch_dashboard.main.dashboard_name
}

output "dashboard_arn" {
  description = "ARN of CloudWatch dashboard"
  value       = aws_cloudwatch_dashboard.main.dashboard_arn
}

# -----------------------------------------------------------------------------
# Alarms
# -----------------------------------------------------------------------------
output "api_5xx_alarm_arn" {
  description = "ARN of API 5xx errors alarm"
  value       = aws_cloudwatch_metric_alarm.api_5xx_errors.arn
}

output "api_latency_alarm_arn" {
  description = "ARN of API latency alarm"
  value       = aws_cloudwatch_metric_alarm.api_latency.arn
}

output "lambda_error_alarm_arns" {
  description = "Map of Lambda error alarm ARNs"
  value       = { for k, v in aws_cloudwatch_metric_alarm.lambda_errors : k => v.arn }
}

output "lambda_duration_alarm_arns" {
  description = "Map of Lambda duration alarm ARNs"
  value       = { for k, v in aws_cloudwatch_metric_alarm.lambda_duration : k => v.arn }
}

output "dynamodb_throttling_alarm_arns" {
  description = "Map of DynamoDB throttling alarm ARNs"
  value       = { for k, v in aws_cloudwatch_metric_alarm.dynamodb_throttling : k => v.arn }
}

# -----------------------------------------------------------------------------
# SNS
# -----------------------------------------------------------------------------
output "sns_topic_arn" {
  description = "ARN of SNS alerts topic (if created)"
  value       = var.create_sns_topic ? aws_sns_topic.alerts[0].arn : null
}

output "sns_topic_name" {
  description = "Name of SNS alerts topic (if created)"
  value       = var.create_sns_topic ? aws_sns_topic.alerts[0].name : null
}

# -----------------------------------------------------------------------------
# All Log Group ARNs (for IAM policies)
# -----------------------------------------------------------------------------
output "all_log_group_arns" {
  description = "List of all log group ARNs managed by this module"
  value = [
    aws_cloudwatch_log_group.api_gateway.arn,
  ]
}
