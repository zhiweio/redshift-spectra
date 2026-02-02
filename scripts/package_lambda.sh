#!/bin/bash
# =============================================================================
# Lambda Packaging Script
# =============================================================================
# This script packages Lambda functions with dependencies in a Docker container
# to ensure compatibility with AWS Lambda's Linux x86_64 runtime.
#
# Usage:
#   ./scripts/package_lambda.sh [--fat|--layer] [--clean]
#
# Options:
#   --fat     Create fat packages with bundled dependencies (for LocalStack)
#   --layer   Create layer + slim packages (default, for production)
#   --clean   Clean previous builds before packaging
#
# Environment Variables:
#   PYTHON_VERSION  Python version to use (default: 3.11)
#   OUTPUT_DIR      Output directory for packages (default: dist/lambda)
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PYTHON_VERSION="${PYTHON_VERSION:-3.11}"
OUTPUT_DIR="${OUTPUT_DIR:-$PROJECT_ROOT/dist/lambda}"
DOCKER_IMAGE="python:${PYTHON_VERSION}-slim-bookworm"

# Package mode
PACKAGE_MODE="layer"  # layer or fat
CLEAN_BUILD=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --fat)
            PACKAGE_MODE="fat"
            shift
            ;;
        --layer)
            PACKAGE_MODE="layer"
            shift
            ;;
        --clean)
            CLEAN_BUILD=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--fat|--layer] [--clean]"
            echo ""
            echo "Options:"
            echo "  --fat     Create fat packages with bundled dependencies (for LocalStack)"
            echo "  --layer   Create layer + slim packages (default, for production)"
            echo "  --clean   Clean previous builds before packaging"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Lambda Packaging Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Mode: ${GREEN}${PACKAGE_MODE}${NC}"
echo -e "Python: ${GREEN}${PYTHON_VERSION}${NC}"
echo -e "Output: ${GREEN}${OUTPUT_DIR}${NC}"
echo ""

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"

# Clean if requested
if [ "$CLEAN_BUILD" = true ]; then
    echo -e "${YELLOW}Cleaning previous builds...${NC}"
    rm -rf "$OUTPUT_DIR"/*.zip "$OUTPUT_DIR"/layer "$OUTPUT_DIR"/deps
    rm -rf "$OUTPUT_DIR"/fat-* "$OUTPUT_DIR"/slim-*
fi

# Generate requirements.txt if needed
if [ ! -f "$PROJECT_ROOT/requirements.txt" ] || \
   [ "$PROJECT_ROOT/pyproject.toml" -nt "$PROJECT_ROOT/requirements.txt" ]; then
    echo -e "${BLUE}Generating requirements.txt from pyproject.toml...${NC}"
    cd "$PROJECT_ROOT"
    if command -v uv &> /dev/null; then
        uv export --no-hashes --no-dev --no-emit-project > requirements.txt
    else
        pip-compile pyproject.toml -o requirements.txt --quiet 2>/dev/null || true
    fi
fi

# Create Docker build script
BUILD_SCRIPT=$(cat << 'DOCKER_BUILD_SCRIPT'
#!/bin/bash
set -euo pipefail

PACKAGE_MODE="$1"
PYTHON_VERSION="$2"

echo "=== Installing dependencies in Docker container ==="
echo "Mode: $PACKAGE_MODE"
echo "Python: $(python --version)"

# Install required system packages
apt-get update -qq && apt-get install -y -qq zip > /dev/null 2>&1

cd /build

# Install pip and upgrade
pip install --upgrade pip --quiet

# Create output directories
mkdir -p /output/deps

if [ "$PACKAGE_MODE" = "fat" ]; then
    echo "=== Building FAT packages (dependencies bundled) ==="

    # Install dependencies
    echo "Installing dependencies..."
    pip install -r requirements.txt -t /output/deps --quiet

    # Remove unnecessary files to reduce size
    echo "Optimizing package size..."
    find /output/deps -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find /output/deps -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
    find /output/deps -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
    find /output/deps -type f -name "*.pyc" -delete 2>/dev/null || true
    find /output/deps -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
    find /output/deps -type d -name "test" -exec rm -rf {} + 2>/dev/null || true
    find /output/deps -type d -name "testing" -exec rm -rf {} + 2>/dev/null || true
    find /output/deps -type d -name "examples" -exec rm -rf {} + 2>/dev/null || true
    find /output/deps -type f -name "*.so" -path "*test*" -delete 2>/dev/null || true

    # Remove large unnecessary packages/files
    rm -rf /output/deps/boto3 /output/deps/botocore 2>/dev/null || true  # Already in Lambda runtime
    rm -rf /output/deps/pip /output/deps/setuptools /output/deps/wheel 2>/dev/null || true
    rm -rf /output/deps/*.dist-info 2>/dev/null || true

    # Show deps size
    echo "Dependencies size: $(du -sh /output/deps | cut -f1)"

    # Create fat packages for each handler
    for handler in api-handler worker authorizer; do
        echo "Creating fat package: ${handler}-fat.zip"
        mkdir -p /output/fat-${handler}
        cp -r /output/deps/* /output/fat-${handler}/ 2>/dev/null || true
        cp -r /build/src/spectra /output/fat-${handler}/spectra
        cd /output/fat-${handler}
        zip -r /output/${handler}-fat.zip . -x "*.pyc" -x "__pycache__/*" -q
        echo "  Size: $(du -h /output/${handler}-fat.zip | cut -f1)"
    done

    # Cleanup temp directories
    rm -rf /output/deps /output/fat-*

else
    echo "=== Building LAYER + SLIM packages ==="

    # Create layer structure
    mkdir -p /output/layer/python

    # Install dependencies into layer
    echo "Installing dependencies into layer..."
    pip install -r requirements.txt -t /output/layer/python --quiet

    # Optimize layer size
    echo "Optimizing layer size..."
    find /output/layer -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find /output/layer -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
    find /output/layer -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
    find /output/layer -type f -name "*.pyc" -delete 2>/dev/null || true
    find /output/layer -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
    find /output/layer -type d -name "test" -exec rm -rf {} + 2>/dev/null || true

    # Create layer zip
    echo "Creating layer.zip..."
    cd /output/layer
    zip -r /output/layer.zip . -x "*.pyc" -x "__pycache__/*" -q
    echo "  Layer size: $(du -h /output/layer.zip | cut -f1)"

    # Create slim packages (code only)
    for handler in api-handler worker authorizer; do
        echo "Creating slim package: ${handler}.zip"
        mkdir -p /output/slim-${handler}
        cp -r /build/src/spectra /output/slim-${handler}/spectra
        cd /output/slim-${handler}
        zip -r /output/${handler}.zip . -x "*.pyc" -x "__pycache__/*" -q
        echo "  Size: $(du -h /output/${handler}.zip | cut -f1)"
    done

    # Cleanup temp directories
    rm -rf /output/layer /output/slim-*
fi

echo ""
echo "=== Build complete ==="
ls -lh /output/*.zip
DOCKER_BUILD_SCRIPT
)

# Run Docker container to build packages
echo -e "${BLUE}Starting Docker build container...${NC}"
echo -e "Image: ${GREEN}${DOCKER_IMAGE}${NC}"
echo ""

docker run --rm \
    --platform linux/amd64 \
    -v "$PROJECT_ROOT:/build:ro" \
    -v "$OUTPUT_DIR:/output" \
    -e PACKAGE_MODE="$PACKAGE_MODE" \
    -e PYTHON_VERSION="$PYTHON_VERSION" \
    "$DOCKER_IMAGE" \
    bash -c "echo '$BUILD_SCRIPT' > /tmp/build.sh && chmod +x /tmp/build.sh && /tmp/build.sh '$PACKAGE_MODE' '$PYTHON_VERSION'"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Packaging complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Output files:"
ls -lh "$OUTPUT_DIR"/*.zip 2>/dev/null || echo "No packages found"
echo ""

if [ "$PACKAGE_MODE" = "fat" ]; then
    echo -e "${YELLOW}Note: Fat packages include all dependencies.${NC}"
    echo -e "${YELLOW}Use these for LocalStack testing.${NC}"
else
    echo -e "${YELLOW}Note: Layer + slim packages created.${NC}"
    echo -e "${YELLOW}Deploy layer.zip as Lambda Layer, then deploy handler zips.${NC}"
fi
