# ============================================================================
# S3 Module - Data Storage for Redshift Spectra
# ============================================================================
# Manages S3 buckets for:
# - Query result exports
# - Bulk import/export data
# - Temporary files
# ============================================================================

# ============================================================================
# Main Data Bucket
# ============================================================================

resource "aws_s3_bucket" "data" {
  bucket = "${var.name_prefix}-data-${var.account_id}"

  # Prevent accidental deletion
  force_destroy = var.force_destroy

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-data"
  })
}

# ============================================================================
# Bucket Versioning
# ============================================================================

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id

  versioning_configuration {
    status = var.enable_versioning ? "Enabled" : "Suspended"
  }
}

# ============================================================================
# Server-Side Encryption
# ============================================================================

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.kms_key_arn != null ? "aws:kms" : "AES256"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = var.kms_key_arn != null
  }
}

# ============================================================================
# Public Access Block
# ============================================================================

resource "aws_s3_bucket_public_access_block" "data" {
  bucket = aws_s3_bucket.data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ============================================================================
# Lifecycle Rules
# ============================================================================

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  count  = var.enable_lifecycle_rules ? 1 : 0
  bucket = aws_s3_bucket.data.id

  # Rule for query results
  rule {
    id     = "expire-query-results"
    status = "Enabled"

    filter {
      prefix = "results/"
    }

    expiration {
      days = var.results_expiration_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }

  # Rule for bulk export data
  rule {
    id     = "expire-bulk-exports"
    status = "Enabled"

    filter {
      prefix = "bulk/exports/"
    }

    expiration {
      days = var.bulk_export_expiration_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }

  # Rule for temporary files
  rule {
    id     = "expire-temp-files"
    status = "Enabled"

    filter {
      prefix = "temp/"
    }

    expiration {
      days = var.temp_files_expiration_days
    }

    # Abort incomplete multipart uploads
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  # Rule for bulk import staging
  rule {
    id     = "expire-bulk-imports"
    status = "Enabled"

    filter {
      prefix = "bulk/imports/"
    }

    expiration {
      days = var.bulk_import_expiration_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 3
    }
  }

  # Intelligent tiering for long-term storage
  rule {
    id     = "intelligent-tiering"
    status = var.enable_intelligent_tiering ? "Enabled" : "Disabled"

    filter {
      prefix = "archive/"
    }

    transition {
      days          = 30
      storage_class = "INTELLIGENT_TIERING"
    }
  }
}

# ============================================================================
# CORS Configuration (for presigned URLs)
# ============================================================================

resource "aws_s3_bucket_cors_configuration" "data" {
  count  = var.enable_cors ? 1 : 0
  bucket = aws_s3_bucket.data.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST", "HEAD"]
    allowed_origins = var.cors_allowed_origins
    expose_headers  = [
      "ETag",
      "Content-Length",
      "Content-Type",
      "x-amz-meta-*"
    ]
    max_age_seconds = 3600
  }
}

# ============================================================================
# Bucket Policy
# ============================================================================

resource "aws_s3_bucket_policy" "data" {
  count  = var.enable_bucket_policy ? 1 : 0
  bucket = aws_s3_bucket.data.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Enforce HTTPS
      {
        Sid       = "EnforceHTTPS"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.data.arn,
          "${aws_s3_bucket.data.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      },
      # Allow Redshift to access for UNLOAD/COPY
      {
        Sid    = "AllowRedshiftAccess"
        Effect = "Allow"
        Principal = {
          Service = "redshift.amazonaws.com"
        }
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:GetBucketAcl",
          "s3:GetBucketCors"
        ]
        Resource = [
          aws_s3_bucket.data.arn,
          "${aws_s3_bucket.data.arn}/*"
        ]
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = var.account_id
          }
        }
      }
    ]
  })
}

# ============================================================================
# Logging Bucket (Optional)
# ============================================================================

resource "aws_s3_bucket" "logs" {
  count  = var.enable_access_logging ? 1 : 0
  bucket = "${var.name_prefix}-logs-${var.account_id}"

  force_destroy = var.force_destroy

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-logs"
  })
}

resource "aws_s3_bucket_versioning" "logs" {
  count  = var.enable_access_logging ? 1 : 0
  bucket = aws_s3_bucket.logs[0].id

  versioning_configuration {
    status = "Suspended"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "logs" {
  count  = var.enable_access_logging ? 1 : 0
  bucket = aws_s3_bucket.logs[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "logs" {
  count  = var.enable_access_logging ? 1 : 0
  bucket = aws_s3_bucket.logs[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "logs" {
  count  = var.enable_access_logging ? 1 : 0
  bucket = aws_s3_bucket.logs[0].id

  rule {
    id     = "expire-logs"
    status = "Enabled"

    expiration {
      days = var.logs_expiration_days
    }
  }
}

resource "aws_s3_bucket_logging" "data" {
  count  = var.enable_access_logging ? 1 : 0
  bucket = aws_s3_bucket.data.id

  target_bucket = aws_s3_bucket.logs[0].id
  target_prefix = "access-logs/"
}
