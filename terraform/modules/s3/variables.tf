# ============================================================================
# S3 Module Variables
# ============================================================================

variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "account_id" {
  description = "AWS account ID"
  type        = string
}

# ============================================================================
# Bucket Configuration
# ============================================================================

variable "force_destroy" {
  description = "Allow bucket to be destroyed even if it contains objects"
  type        = bool
  default     = false
}

variable "enable_versioning" {
  description = "Enable versioning on the data bucket"
  type        = bool
  default     = true
}

# ============================================================================
# Encryption
# ============================================================================

variable "kms_key_arn" {
  description = "ARN of KMS key for encryption (optional, uses AES256 if not specified)"
  type        = string
  default     = null
}

# ============================================================================
# Lifecycle Configuration
# ============================================================================

variable "enable_lifecycle_rules" {
  description = "Enable lifecycle rules for automatic cleanup"
  type        = bool
  default     = true
}

variable "results_expiration_days" {
  description = "Days before query results expire"
  type        = number
  default     = 7
}

variable "bulk_export_expiration_days" {
  description = "Days before bulk export files expire"
  type        = number
  default     = 30
}

variable "bulk_import_expiration_days" {
  description = "Days before bulk import staging files expire"
  type        = number
  default     = 7
}

variable "temp_files_expiration_days" {
  description = "Days before temporary files expire"
  type        = number
  default     = 1
}

variable "enable_intelligent_tiering" {
  description = "Enable intelligent tiering for archive prefix"
  type        = bool
  default     = false
}

# ============================================================================
# CORS Configuration
# ============================================================================

variable "enable_cors" {
  description = "Enable CORS for presigned URL access"
  type        = bool
  default     = true
}

variable "cors_allowed_origins" {
  description = "List of allowed origins for CORS"
  type        = list(string)
  default     = ["*"]
}

# ============================================================================
# Bucket Policy
# ============================================================================

variable "enable_bucket_policy" {
  description = "Enable bucket policy for Redshift access"
  type        = bool
  default     = true
}

# ============================================================================
# Access Logging
# ============================================================================

variable "enable_access_logging" {
  description = "Enable access logging to a separate bucket"
  type        = bool
  default     = false
}

variable "logs_expiration_days" {
  description = "Days before access logs expire"
  type        = number
  default     = 90
}

# ============================================================================
# Tags
# ============================================================================

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
