#!/bin/bash
# =============================================================================
# LocalStack Environment Deploy Script
# =============================================================================
# Helper script to deploy Terragrunt configurations to LocalStack.
#
# Usage:
#   ./scripts/localstack-deploy.sh [command] [module]
#
# Commands:
#   start    - Start LocalStack container
#   stop     - Stop LocalStack container
#   deploy   - Deploy all modules to LocalStack
#   destroy  - Destroy all resources in LocalStack
#   apply    - Apply specific module (e.g., ./scripts/localstack-deploy.sh apply dynamodb)
#   plan     - Plan specific module
#   status   - Check LocalStack status
#
# Examples:
#   ./scripts/localstack-deploy.sh start
#   ./scripts/localstack-deploy.sh deploy
#   ./scripts/localstack-deploy.sh apply s3
#   ./scripts/localstack-deploy.sh destroy
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TERRAGRUNT_DIR="${PROJECT_ROOT}/terragrunt/environments/local/us-east-1"
TERRAGRUNT_CONFIG="${PROJECT_ROOT}/terragrunt/terragrunt-local.hcl"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored message
print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if LocalStack is running
check_localstack() {
    if curl -s http://localhost:4566/_localstack/health > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Wait for LocalStack to be ready
wait_for_localstack() {
    print_info "Waiting for LocalStack to be ready..."
    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if check_localstack; then
            print_success "LocalStack is ready!"
            return 0
        fi
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done

    print_error "LocalStack failed to start after ${max_attempts} attempts"
    return 1
}

# Start LocalStack
cmd_start() {
    print_info "Starting LocalStack..."
    cd "${PROJECT_ROOT}"

    if check_localstack; then
        print_warning "LocalStack is already running"
        return 0
    fi

    docker compose up -d localstack
    wait_for_localstack

    print_success "LocalStack started successfully"
    echo ""
    echo "LocalStack endpoint: http://localhost:4566"
    echo "Health check: http://localhost:4566/_localstack/health"
}

# Stop LocalStack
cmd_stop() {
    print_info "Stopping LocalStack..."
    cd "${PROJECT_ROOT}"
    docker compose down
    print_success "LocalStack stopped"
}

# Check LocalStack status
cmd_status() {
    if check_localstack; then
        print_success "LocalStack is running"
        echo ""
        echo "Health status:"
        curl -s http://localhost:4566/_localstack/health | python3 -m json.tool 2>/dev/null || \
            curl -s http://localhost:4566/_localstack/health
    else
        print_warning "LocalStack is not running"
        echo "Start it with: $0 start"
    fi
}

# Deploy all modules
cmd_deploy() {
    if ! check_localstack; then
        print_error "LocalStack is not running. Start it with: $0 start"
        exit 1
    fi

    print_info "Deploying all modules to LocalStack..."
    cd "${TERRAGRUNT_DIR}"

    # Set environment variables for LocalStack
    export AWS_ACCESS_KEY_ID="test"
    export AWS_SECRET_ACCESS_KEY="test"
    export AWS_DEFAULT_REGION="us-east-1"

    terragrunt run --all \
        --config "${TERRAGRUNT_CONFIG}" \
        --non-interactive \
        -- apply -auto-approve

    print_success "All modules deployed successfully!"
}

# Destroy all resources
cmd_destroy() {
    if ! check_localstack; then
        print_warning "LocalStack is not running, but proceeding with state cleanup..."
    fi

    print_warning "This will destroy all resources in LocalStack"
    read -p "Are you sure? (y/N) " -n 1 -r
    echo

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Cancelled"
        exit 0
    fi

    cd "${TERRAGRUNT_DIR}"

    export AWS_ACCESS_KEY_ID="test"
    export AWS_SECRET_ACCESS_KEY="test"
    export AWS_DEFAULT_REGION="us-east-1"

    terragrunt run --all \
        --config "${TERRAGRUNT_CONFIG}" \
        --non-interactive \
        -- destroy -auto-approve

    print_success "All resources destroyed"
}

# Apply specific module
cmd_apply() {
    local module="$1"

    if [ -z "$module" ]; then
        print_error "Module name required. Usage: $0 apply <module>"
        echo "Available modules: dynamodb, s3, iam, lambda, monitoring, api-gateway"
        exit 1
    fi

    if ! check_localstack; then
        print_error "LocalStack is not running. Start it with: $0 start"
        exit 1
    fi

    local module_dir="${TERRAGRUNT_DIR}/${module}"

    if [ ! -d "$module_dir" ]; then
        print_error "Module not found: $module"
        echo "Available modules:"
        ls -1 "${TERRAGRUNT_DIR}" | grep -v "\.hcl$"
        exit 1
    fi

    print_info "Applying module: ${module}"
    cd "${module_dir}"

    export AWS_ACCESS_KEY_ID="test"
    export AWS_SECRET_ACCESS_KEY="test"
    export AWS_DEFAULT_REGION="us-east-1"

    terragrunt apply \
        --config "${TERRAGRUNT_CONFIG}" \
        --auto-approve

    print_success "Module ${module} applied successfully!"
}

# Plan specific module
cmd_plan() {
    local module="$1"

    if [ -z "$module" ]; then
        print_error "Module name required. Usage: $0 plan <module>"
        exit 1
    fi

    if ! check_localstack; then
        print_error "LocalStack is not running. Start it with: $0 start"
        exit 1
    fi

    local module_dir="${TERRAGRUNT_DIR}/${module}"

    if [ ! -d "$module_dir" ]; then
        print_error "Module not found: $module"
        exit 1
    fi

    print_info "Planning module: ${module}"
    cd "${module_dir}"

    export AWS_ACCESS_KEY_ID="test"
    export AWS_SECRET_ACCESS_KEY="test"
    export AWS_DEFAULT_REGION="us-east-1"

    terragrunt plan --config "${TERRAGRUNT_CONFIG}"
}

# Show usage
show_usage() {
    echo "LocalStack Environment Deploy Script"
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  start         Start LocalStack container"
    echo "  stop          Stop LocalStack container"
    echo "  status        Check LocalStack status"
    echo "  deploy        Deploy all modules to LocalStack"
    echo "  destroy       Destroy all resources in LocalStack"
    echo "  apply <mod>   Apply specific module"
    echo "  plan <mod>    Plan specific module"
    echo ""
    echo "Available modules: dynamodb, s3, iam, lambda, monitoring, api-gateway"
    echo ""
    echo "Deploy order: s3 -> dynamodb -> iam -> lambda -> monitoring -> api-gateway"
    echo ""
    echo "Examples:"
    echo "  $0 start"
    echo "  $0 deploy"
    echo "  $0 apply lambda"
    echo "  $0 status"
}

# Main
case "${1:-}" in
    start)
        cmd_start
        ;;
    stop)
        cmd_stop
        ;;
    status)
        cmd_status
        ;;
    deploy)
        cmd_deploy
        ;;
    destroy)
        cmd_destroy
        ;;
    apply)
        cmd_apply "$2"
        ;;
    plan)
        cmd_plan "$2"
        ;;
    *)
        show_usage
        exit 1
        ;;
esac
