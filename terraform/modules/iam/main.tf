# ============================================================================
# IAM Module - Roles and Policies for Redshift Spectra
# ============================================================================

# ============================================================================
# Lambda Execution Role - Authorizer
# ============================================================================

resource "aws_iam_role" "authorizer" {
  name = "${var.name_prefix}-authorizer-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
  
  tags = var.tags
}

resource "aws_iam_role_policy" "authorizer_secrets" {
  name = "${var.name_prefix}-authorizer-secrets"
  role = aws_iam_role.authorizer.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = var.secrets_arn_prefix
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "authorizer_basic" {
  role       = aws_iam_role.authorizer.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ============================================================================
# Lambda Execution Role - API Handler
# ============================================================================

resource "aws_iam_role" "api_handler" {
  name = "${var.name_prefix}-api-handler-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
  
  tags = var.tags
}

resource "aws_iam_role_policy" "api_handler_redshift" {
  name = "${var.name_prefix}-api-redshift"
  role = aws_iam_role.api_handler.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "RedshiftDataAPI"
        Effect = "Allow"
        Action = [
          "redshift-data:ExecuteStatement",
          "redshift-data:BatchExecuteStatement",
          "redshift-data:DescribeStatement",
          "redshift-data:GetStatementResult",
          "redshift-data:CancelStatement",
          "redshift-data:ListStatements"
        ]
        Resource = "*"
      },
      {
        Sid    = "RedshiftServerless"
        Effect = "Allow"
        Action = [
          "redshift-serverless:GetCredentials"
        ]
        Resource = [
          var.redshift_workgroup_arn,
          var.redshift_namespace_arn
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "api_handler_dynamodb" {
  name = "${var.name_prefix}-api-dynamodb"
  role = aws_iam_role.api_handler.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = concat(
          var.dynamodb_table_arns,
          [for arn in var.dynamodb_table_arns : "${arn}/index/*"]
        )
      }
    ]
  })
}

resource "aws_iam_role_policy" "api_handler_s3" {
  name = "${var.name_prefix}-api-s3"
  role = aws_iam_role.api_handler.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          var.s3_bucket_arn,
          "${var.s3_bucket_arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "api_handler_secrets" {
  name = "${var.name_prefix}-api-secrets"
  role = aws_iam_role.api_handler.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = var.secrets_arn_prefix
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "api_handler_basic" {
  role       = aws_iam_role.api_handler.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "api_handler_vpc" {
  count      = var.enable_vpc ? 1 : 0
  role       = aws_iam_role.api_handler.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# ============================================================================
# Lambda Execution Role - Worker (Background Jobs)
# ============================================================================

resource "aws_iam_role" "worker" {
  name = "${var.name_prefix}-worker-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
  
  tags = var.tags
}

resource "aws_iam_role_policy" "worker_redshift" {
  name = "${var.name_prefix}-worker-redshift"
  role = aws_iam_role.worker.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "RedshiftDataAPI"
        Effect = "Allow"
        Action = [
          "redshift-data:ExecuteStatement",
          "redshift-data:BatchExecuteStatement",
          "redshift-data:DescribeStatement",
          "redshift-data:GetStatementResult",
          "redshift-data:CancelStatement",
          "redshift-data:ListStatements"
        ]
        Resource = "*"
      },
      {
        Sid    = "RedshiftServerless"
        Effect = "Allow"
        Action = [
          "redshift-serverless:GetCredentials"
        ]
        Resource = [
          var.redshift_workgroup_arn,
          var.redshift_namespace_arn
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "worker_dynamodb" {
  name = "${var.name_prefix}-worker-dynamodb"
  role = aws_iam_role.worker.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = concat(
          var.dynamodb_table_arns,
          [for arn in var.dynamodb_table_arns : "${arn}/index/*"]
        )
      }
    ]
  })
}

resource "aws_iam_role_policy" "worker_s3" {
  name = "${var.name_prefix}-worker-s3"
  role = aws_iam_role.worker.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = [
          var.s3_bucket_arn,
          "${var.s3_bucket_arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "worker_basic" {
  role       = aws_iam_role.worker.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "worker_vpc" {
  count      = var.enable_vpc ? 1 : 0
  role       = aws_iam_role.worker.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# ============================================================================
# KMS Access (Optional)
# ============================================================================

resource "aws_iam_role_policy" "api_handler_kms" {
  count = var.kms_key_arn != null ? 1 : 0
  name  = "${var.name_prefix}-api-kms"
  role  = aws_iam_role.api_handler.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = var.kms_key_arn
      }
    ]
  })
}

resource "aws_iam_role_policy" "worker_kms" {
  count = var.kms_key_arn != null ? 1 : 0
  name  = "${var.name_prefix}-worker-kms"
  role  = aws_iam_role.worker.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = var.kms_key_arn
      }
    ]
  })
}

# ============================================================================
# Redshift UNLOAD/COPY IAM Role
# ============================================================================

resource "aws_iam_role" "redshift_s3" {
  name = "${var.name_prefix}-redshift-s3-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "redshift.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
  
  tags = var.tags
}

resource "aws_iam_role_policy" "redshift_s3_access" {
  name = "${var.name_prefix}-redshift-s3-access"
  role = aws_iam_role.redshift_s3.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = [
          var.s3_bucket_arn,
          "${var.s3_bucket_arn}/*"
        ]
      }
    ]
  })
}
