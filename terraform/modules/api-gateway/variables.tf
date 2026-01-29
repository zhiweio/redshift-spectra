# =============================================================================
# API Gateway Module Variables
# =============================================================================

variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# -----------------------------------------------------------------------------
# Lambda Integration
# -----------------------------------------------------------------------------
variable "query_lambda_invoke_arn" {
  description = "Invoke ARN of the Query Lambda function"
  type        = string
}

variable "query_lambda_function_name" {
  description = "Name of the Query Lambda function"
  type        = string
}

variable "status_lambda_invoke_arn" {
  description = "Invoke ARN of the Status Lambda function"
  type        = string
}

variable "status_lambda_function_name" {
  description = "Name of the Status Lambda function"
  type        = string
}

variable "result_lambda_invoke_arn" {
  description = "Invoke ARN of the Result Lambda function"
  type        = string
}

variable "result_lambda_function_name" {
  description = "Name of the Result Lambda function"
  type        = string
}

variable "bulk_lambda_invoke_arn" {
  description = "Invoke ARN of the Bulk Lambda function"
  type        = string
}

variable "bulk_lambda_function_name" {
  description = "Name of the Bulk Lambda function"
  type        = string
}

# -----------------------------------------------------------------------------
# Authorization
# -----------------------------------------------------------------------------
variable "enable_lambda_authorizer" {
  description = "Enable Lambda authorizer instead of IAM"
  type        = bool
  default     = false
}

variable "authorizer_lambda_invoke_arn" {
  description = "Invoke ARN of the Authorizer Lambda function"
  type        = string
  default     = null
}

variable "authorizer_role_arn" {
  description = "IAM role ARN for the authorizer"
  type        = string
  default     = null
}

variable "authorizer_cache_ttl" {
  description = "TTL for authorizer cache in seconds"
  type        = number
  default     = 300
}

# -----------------------------------------------------------------------------
# Logging & Monitoring
# -----------------------------------------------------------------------------
variable "access_log_group_arn" {
  description = "ARN of CloudWatch Log Group for access logs"
  type        = string
}

variable "logging_level" {
  description = "Logging level for API Gateway (OFF, ERROR, INFO)"
  type        = string
  default     = "INFO"
}

variable "enable_xray_tracing" {
  description = "Enable X-Ray tracing"
  type        = bool
  default     = true
}

# -----------------------------------------------------------------------------
# Throttling & Caching
# -----------------------------------------------------------------------------
variable "throttling_burst_limit" {
  description = "Throttling burst limit"
  type        = number
  default     = 5000
}

variable "throttling_rate_limit" {
  description = "Throttling rate limit"
  type        = number
  default     = 10000
}

variable "enable_caching" {
  description = "Enable API Gateway caching"
  type        = bool
  default     = false
}

variable "cache_ttl" {
  description = "Cache TTL in seconds"
  type        = number
  default     = 300
}

# -----------------------------------------------------------------------------
# WAF
# -----------------------------------------------------------------------------
variable "waf_acl_arn" {
  description = "ARN of WAF Web ACL to associate"
  type        = string
  default     = null
}

# -----------------------------------------------------------------------------
# Custom Domain
# -----------------------------------------------------------------------------
variable "custom_domain_name" {
  description = "Custom domain name for the API"
  type        = string
  default     = null
}

variable "certificate_arn" {
  description = "ACM certificate ARN for custom domain"
  type        = string
  default     = null
}

variable "base_path" {
  description = "Base path for custom domain mapping"
  type        = string
  default     = ""
}
