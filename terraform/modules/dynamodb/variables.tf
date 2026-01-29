# ============================================================================
# DynamoDB Module Variables
# ============================================================================

variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

# ============================================================================
# Jobs Table Configuration
# ============================================================================

variable "jobs_table_billing_mode" {
  description = "Billing mode for jobs table (PROVISIONED or PAY_PER_REQUEST)"
  type        = string
  default     = "PAY_PER_REQUEST"

  validation {
    condition     = contains(["PROVISIONED", "PAY_PER_REQUEST"], var.jobs_table_billing_mode)
    error_message = "Billing mode must be either PROVISIONED or PAY_PER_REQUEST."
  }
}

variable "jobs_table_read_capacity" {
  description = "Read capacity units for jobs table (only used with PROVISIONED billing)"
  type        = number
  default     = 5
}

variable "jobs_table_write_capacity" {
  description = "Write capacity units for jobs table (only used with PROVISIONED billing)"
  type        = number
  default     = 5
}

# ============================================================================
# Sessions Table Configuration
# ============================================================================

variable "sessions_table_billing_mode" {
  description = "Billing mode for sessions table (PROVISIONED or PAY_PER_REQUEST)"
  type        = string
  default     = "PAY_PER_REQUEST"

  validation {
    condition     = contains(["PROVISIONED", "PAY_PER_REQUEST"], var.sessions_table_billing_mode)
    error_message = "Billing mode must be either PROVISIONED or PAY_PER_REQUEST."
  }
}

variable "sessions_table_read_capacity" {
  description = "Read capacity units for sessions table (only used with PROVISIONED billing)"
  type        = number
  default     = 5
}

variable "sessions_table_write_capacity" {
  description = "Write capacity units for sessions table (only used with PROVISIONED billing)"
  type        = number
  default     = 5
}

# ============================================================================
# TTL Configuration
# ============================================================================

variable "jobs_ttl_days" {
  description = "Number of days before job records expire"
  type        = number
  default     = 30
}

variable "sessions_ttl_hours" {
  description = "Number of hours before session records expire"
  type        = number
  default     = 24
}

# ============================================================================
# Security Configuration
# ============================================================================

variable "enable_point_in_time_recovery" {
  description = "Enable point-in-time recovery for DynamoDB tables"
  type        = bool
  default     = true
}

variable "kms_key_arn" {
  description = "ARN of KMS key for encryption (optional, uses AWS managed key if not specified)"
  type        = string
  default     = null
}

# ============================================================================
# Tags
# ============================================================================

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
