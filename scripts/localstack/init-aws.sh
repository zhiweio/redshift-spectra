#!/bin/bash
# =============================================================================
# LocalStack Initialization Script
# =============================================================================
# This script runs when LocalStack container starts.
# It pre-configures resources that Terraform might need.
# =============================================================================

set -e

echo "========================================"
echo "LocalStack Initialization Script"
echo "========================================"

# Wait for LocalStack to be ready
echo "Waiting for LocalStack services..."
awslocal sts get-caller-identity > /dev/null 2>&1 || true

echo "LocalStack is ready!"
echo "Region: ${AWS_DEFAULT_REGION:-us-east-1}"
echo "Endpoint: http://localhost:4566"

# Create a marker file to indicate initialization is complete
touch /tmp/localstack-initialized

echo "========================================"
echo "Initialization Complete!"
echo "========================================"
echo ""
echo "You can now deploy resources using Terragrunt:"
echo "  cd terragrunt/environments/local/us-east-1"
echo "  terragrunt run --all apply --config ../../terragrunt-local.hcl"
echo ""
