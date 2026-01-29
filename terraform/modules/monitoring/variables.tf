# =============================================================================
# Monitoring Module Variables
# =============================================================================

variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# -----------------------------------------------------------------------------
# Log Retention
# -----------------------------------------------------------------------------
variable "log_retention_days" {
  description = "Number of days to retain CloudWatch logs"
  type        = number
  default     = 30
}

# -----------------------------------------------------------------------------
# Alarm Thresholds
# -----------------------------------------------------------------------------
variable "api_error_threshold" {
  description = "Threshold for API 5xx errors per minute"
  type        = number
  default     = 10
}

variable "api_latency_threshold_ms" {
  description = "Threshold for API p99 latency in milliseconds"
  type        = number
  default     = 5000
}

variable "lambda_error_threshold" {
  description = "Threshold for Lambda errors per minute"
  type        = number
  default     = 5
}

variable "lambda_duration_threshold_ms" {
  description = "Threshold for Lambda p95 duration in milliseconds"
  type        = number
  default     = 25000
}

# -----------------------------------------------------------------------------
# Lambda Functions (for alarms and dashboards)
# -----------------------------------------------------------------------------
variable "lambda_function_names" {
  description = "Map of Lambda function names for monitoring"
  type = object({
    api        = string
    worker     = string
    authorizer = string
  })
  default = null
}

variable "lambda_log_group_names" {
  description = "Map of Lambda CloudWatch log group names for Insights queries"
  type = object({
    api        = string
    worker     = string
    authorizer = string
  })
  default = null
}

# -----------------------------------------------------------------------------
# Alarm Actions
# -----------------------------------------------------------------------------
variable "alarm_actions" {
  description = "List of ARNs to notify when alarm triggers"
  type        = list(string)
  default     = []
}

variable "ok_actions" {
  description = "List of ARNs to notify when alarm returns to OK"
  type        = list(string)
  default     = []
}

# -----------------------------------------------------------------------------
# SNS
# -----------------------------------------------------------------------------
variable "create_sns_topic" {
  description = "Create SNS topic for alerts"
  type        = bool
  default     = true
}

variable "alert_email" {
  description = "Email address for alert notifications"
  type        = string
  default     = null
}

# -----------------------------------------------------------------------------
# X-Ray
# -----------------------------------------------------------------------------
variable "enable_xray_tracing" {
  description = "Enable X-Ray distributed tracing"
  type        = bool
  default     = true
}
