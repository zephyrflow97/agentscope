# -*- coding: utf-8 -*-
"""The pack command module for AgentScope platform.

This module implements the `agentscope pack` command that packages
applications for deployment on the platform.
"""
import argparse
import os
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

from .manifest import (
    MANIFEST_FILENAME,
    parse_manifest,
    validate_entrypoint,
)


DOCKERFILE_TEMPLATE = '''FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \\
    gcc \\
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run the platform runtime
CMD ["python", "-m", "agentscope.platform.runtime"]
'''


def _create_dockerfile(app_dir: str, force: bool = False) -> str:
    """Create a Dockerfile if it doesn't exist.

    Args:
        app_dir: Application directory.
        force: Whether to overwrite existing Dockerfile.

    Returns:
        Path to the Dockerfile.
    """
    dockerfile_path = os.path.join(app_dir, "Dockerfile")

    if os.path.exists(dockerfile_path) and not force:
        return dockerfile_path

    with open(dockerfile_path, "w", encoding="utf-8") as f:
        f.write(DOCKERFILE_TEMPLATE)

    return dockerfile_path


def _ensure_requirements(app_dir: str) -> str:
    """Ensure requirements.txt exists.

    Args:
        app_dir: Application directory.

    Returns:
        Path to requirements.txt.

    Raises:
        FileNotFoundError: If requirements.txt doesn't exist.
    """
    requirements_path = os.path.join(app_dir, "requirements.txt")

    if not os.path.exists(requirements_path):
        # Create a minimal requirements.txt with agentscope
        with open(requirements_path, "w", encoding="utf-8") as f:
            f.write("agentscope\n")
        print(f"Created minimal requirements.txt at {requirements_path}")

    return requirements_path


def _collect_files(app_dir: str) -> list[str]:
    """Collect all files to be packaged.

    Args:
        app_dir: Application directory.

    Returns:
        List of file paths relative to app_dir.
    """
    files = []
    app_path = Path(app_dir)

    # Patterns to exclude
    exclude_patterns = {
        "__pycache__",
        ".git",
        ".gitignore",
        ".env",
        "*.pyc",
        "*.pyo",
        "*.egg-info",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "venv",
        ".venv",
        "env",
        "node_modules",
    }

    for root, dirs, filenames in os.walk(app_dir):
        # Filter out excluded directories
        dirs[:] = [
            d for d in dirs
            if d not in exclude_patterns
            and not d.startswith(".")
        ]

        rel_root = os.path.relpath(root, app_dir)

        for filename in filenames:
            # Skip excluded patterns
            if any(
                filename.endswith(p.replace("*", ""))
                for p in exclude_patterns
                if "*" in p
            ):
                continue
            if filename in exclude_patterns:
                continue
            if filename.startswith("."):
                continue

            if rel_root == ".":
                files.append(filename)
            else:
                files.append(os.path.join(rel_root, filename))

    return files


def pack(
    app_dir: str,
    output: str | None = None,
    validate: bool = True,
    force_dockerfile: bool = False,
) -> str:
    """Package an AgentScope application for platform deployment.

    Args:
        app_dir: Directory containing the application.
        output: Output path for the tarball. If None, uses
            "{app_name}-{version}.tar.gz" in current directory.
        validate: Whether to validate the entrypoint.
        force_dockerfile: Whether to overwrite existing Dockerfile.

    Returns:
        Path to the created tarball.

    Raises:
        FileNotFoundError: If manifest or required files are missing.
        ValueError: If manifest or entrypoint is invalid.
    """
    app_dir = os.path.abspath(app_dir)

    # Parse and validate manifest
    print(f"Parsing manifest from {app_dir}...")
    manifest = parse_manifest(app_dir)
    print(f"  Application: {manifest.name} v{manifest.version}")

    # Validate entrypoint
    if validate:
        print("Validating entrypoint...")
        validate_entrypoint(manifest, app_dir)
        print(
            f"  Entrypoint: {manifest.entrypoint.module}:"
            f"{manifest.entrypoint.factory}"
        )

    # Ensure Dockerfile exists
    print("Checking Dockerfile...")
    dockerfile_path = _create_dockerfile(app_dir, force_dockerfile)
    if force_dockerfile:
        print(f"  Created Dockerfile at {dockerfile_path}")
    else:
        print(f"  Using existing Dockerfile at {dockerfile_path}")

    # Ensure requirements.txt exists
    print("Checking requirements.txt...")
    _ensure_requirements(app_dir)

    # Determine output path
    if output is None:
        output = f"{manifest.name}-{manifest.version}.tar.gz"
    output = os.path.abspath(output)

    # Collect files
    print("Collecting files...")
    files = _collect_files(app_dir)
    print(f"  Found {len(files)} files to package")

    # Create tarball
    print(f"Creating package: {output}...")
    with tarfile.open(output, "w:gz") as tar:
        for file in files:
            full_path = os.path.join(app_dir, file)
            tar.add(full_path, arcname=file)

    print(f"Package created successfully: {output}")
    return output


def main(args: list[str] | None = None) -> int:
    """Main entry point for the pack command.

    Args:
        args: Command line arguments. If None, uses sys.argv.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        prog="agentscope pack",
        description="Package an AgentScope application for platform deployment",
    )
    parser.add_argument(
        "app_dir",
        nargs="?",
        default=".",
        help="Application directory (default: current directory)",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output path for the tarball",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip entrypoint validation",
    )
    parser.add_argument(
        "--force-dockerfile",
        action="store_true",
        help="Overwrite existing Dockerfile with template",
    )

    parsed_args = parser.parse_args(args)

    try:
        pack(
            app_dir=parsed_args.app_dir,
            output=parsed_args.output,
            validate=not parsed_args.no_validate,
            force_dockerfile=parsed_args.force_dockerfile,
        )
        return 0
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
