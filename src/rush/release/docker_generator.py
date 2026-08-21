"""Multi-stage distroless non-root Dockerfile generator."""

from __future__ import annotations

from pathlib import Path

HARDENED_DOCKERFILE = """# Multi-stage hardened build for Rush CLI / MCP Server
FROM python:3.12-slim-bookworm AS builder

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \\
    PYTHONDONTWRITEBYTECODE=1 \\
    PIP_NO_CACHE_DIR=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN uv pip install --system --no-cache .

# Final minimal production runtime
FROM gcr.io/distroless/python3-debian12:nonroot

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /app /app

USER nonroot:nonroot

ENTRYPOINT ["python3", "-m", "rush.cli"]
CMD ["mcp", "serve"]
"""


class DockerfileGenerator:
    """Generates hardened, multi-stage, distroless Dockerfiles."""

    @staticmethod
    def generate_dockerfile(repo_root: Path) -> Path:
        dockerfile_path = repo_root / "Dockerfile"
        dockerfile_path.write_text(HARDENED_DOCKERFILE, encoding="utf-8")
        return dockerfile_path
