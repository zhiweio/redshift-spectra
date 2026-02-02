#!/usr/bin/env python3
"""
Lambda Layer Builder Script

This script builds Lambda layers with proper architecture compatibility
using Docker with Amazon Linux 2 to ensure Lambda runtime compatibility.

Features:
- Generates requirements.txt from pyproject.toml using uv
- Uses Docker for Amazon Linux 2 compatibility
- Optimizes layer size by removing unnecessary files
- Validates layer size constraints

Usage:
    python scripts/build_layer.py [--output dist/lambda/layer.zip]
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

# AWS Lambda Layer constraints
MAX_LAYER_SIZE_ZIPPED = 50 * 1024 * 1024  # 50 MB
MAX_LAYER_SIZE_UNZIPPED = 250 * 1024 * 1024  # 250 MB


def run_command(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result


def generate_requirements(project_root: Path) -> Path:
    """Generate requirements.txt from pyproject.toml using uv."""
    requirements_path = project_root / "requirements.txt"

    print("Generating requirements.txt from pyproject.toml...")
    result = run_command(
        ["uv", "export", "--no-hashes", "--no-dev", "--no-emit-project"],
        cwd=str(project_root),
    )

    requirements_path.write_text(result.stdout)
    print(f"Generated: {requirements_path}")
    return requirements_path


def build_layer_docker(requirements_path: Path, output_dir: Path) -> None:
    """Build layer using Docker with Amazon Linux 2."""
    python_dir = output_dir / "python"
    python_dir.mkdir(parents=True, exist_ok=True)

    # Create temporary directory for Docker build
    with tempfile.TemporaryDirectory() as tmpdir:
        # Copy requirements to temp dir
        tmp_requirements = Path(tmpdir) / "requirements.txt"
        shutil.copy(requirements_path, tmp_requirements)

        # Create Dockerfile
        dockerfile = Path(tmpdir) / "Dockerfile"
        dockerfile.write_text("""
FROM public.ecr.aws/lambda/python:3.11

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt -t /opt/python --quiet
""")

        print("Building layer using Docker (Amazon Linux 2)...")

        # Build Docker image
        run_command(["docker", "build", "-t", "lambda-layer-builder", str(tmpdir)])

        # Extract layer from container
        run_command(["docker", "create", "--name", "layer-container", "lambda-layer-builder"])

        try:
            run_command(["docker", "cp", "layer-container:/opt/python/.", str(python_dir)])
        finally:
            run_command(["docker", "rm", "layer-container"])


def optimize_layer(layer_dir: Path) -> None:
    """Remove unnecessary files to reduce layer size."""
    print("Optimizing layer size...")

    removed_size = 0

    for pattern in ["__pycache__", "*.pyc", "*.pyo", "tests", "test"]:
        for path in layer_dir.rglob(pattern):
            if path.is_dir():
                size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
                shutil.rmtree(path, ignore_errors=True)
            elif path.is_file():
                size = path.stat().st_size
                path.unlink(missing_ok=True)
            else:
                continue
            removed_size += size

    # Remove dist-info and egg-info directories
    for info_dir in layer_dir.rglob("*.dist-info"):
        if info_dir.is_dir():
            size = sum(f.stat().st_size for f in info_dir.rglob("*") if f.is_file())
            shutil.rmtree(info_dir, ignore_errors=True)
            removed_size += size

    for info_dir in layer_dir.rglob("*.egg-info"):
        if info_dir.is_dir():
            size = sum(f.stat().st_size for f in info_dir.rglob("*") if f.is_file())
            shutil.rmtree(info_dir, ignore_errors=True)
            removed_size += size

    print(f"Removed {removed_size / 1024 / 1024:.2f} MB of unnecessary files")


def create_zip(source_dir: Path, output_path: Path) -> int:
    """Create a zip file from a directory."""
    print(f"Creating zip: {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(source_dir)
                zf.write(file_path, arcname)

    return output_path.stat().st_size


def validate_layer(zip_path: Path) -> bool:
    """Validate layer size constraints."""
    zip_size = zip_path.stat().st_size

    print("\nLayer validation:")
    print(f"  Zipped size: {zip_size / 1024 / 1024:.2f} MB (limit: 50 MB)")

    if zip_size > MAX_LAYER_SIZE_ZIPPED:
        print("  ❌ ERROR: Layer exceeds 50 MB limit!")
        return False

    # Calculate unzipped size
    with zipfile.ZipFile(zip_path, "r") as zf:
        unzipped_size = sum(info.file_size for info in zf.filelist)

    print(f"  Unzipped size: {unzipped_size / 1024 / 1024:.2f} MB (limit: 250 MB)")

    if unzipped_size > MAX_LAYER_SIZE_UNZIPPED:
        print("  ❌ ERROR: Layer exceeds 250 MB unzipped limit!")
        return False

    print("  ✅ Layer size OK!")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Lambda layer with dependencies from pyproject.toml using Docker"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("dist/lambda/layer.zip"),
        help="Output path for the layer zip file",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip layer size validation",
    )
    args = parser.parse_args()

    # Determine project root
    project_root = Path(__file__).parent.parent.resolve()
    os.chdir(project_root)

    print(f"Project root: {project_root}")
    print(f"Output: {args.output}")
    print("Build method: Docker (Amazon Linux 2)")
    print("-" * 50)

    # Generate requirements.txt
    requirements_path = generate_requirements(project_root)

    # Create temporary build directory
    with tempfile.TemporaryDirectory() as tmpdir:
        build_dir = Path(tmpdir) / "layer"
        build_dir.mkdir()

        # Build layer using Docker
        build_layer_docker(requirements_path, build_dir)

        # Optimize layer
        optimize_layer(build_dir)

        # Create zip
        zip_size = create_zip(build_dir, args.output)
        print(f"Layer created: {args.output} ({zip_size / 1024 / 1024:.2f} MB)")

    # Validate
    if not args.skip_validation and not validate_layer(args.output):
        sys.exit(1)

    # Clean up requirements.txt (it's in .gitignore)
    print("\n✅ Layer build complete!")


if __name__ == "__main__":
    main()
