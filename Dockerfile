# =============================================================================
# WTracker Dockerfile
# Multi-stage build for efficient production images
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Base image with Python and system dependencies
# -----------------------------------------------------------------------------
FROM python:3.11-slim as base

# Prevent Python from writing bytecode and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# -----------------------------------------------------------------------------
# Stage 2: Builder - install Python dependencies
# -----------------------------------------------------------------------------
FROM base as builder

# Install pip and build tools
RUN pip install --upgrade pip setuptools wheel

# Copy dependency files and source for package discovery
COPY pyproject.toml README.md ./
COPY src ./src

# Install dependencies into a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install production dependencies
RUN pip install --no-cache-dir .

# -----------------------------------------------------------------------------
# Stage 3: Development image
# -----------------------------------------------------------------------------
FROM base as development

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code first (needed for dev dependencies install)
COPY . .

# Install development dependencies
RUN pip install --no-cache-dir ".[dev]"

# Install Playwright browsers for scraping
RUN playwright install chromium && playwright install-deps chromium

# Expose port
EXPOSE 8000

# Development server with hot reload
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# -----------------------------------------------------------------------------
# Stage 4: Production image
# -----------------------------------------------------------------------------
FROM base as production

# Create non-root user for security
RUN groupadd --gid 1000 wtracker \
    && useradd --uid 1000 --gid wtracker --shell /bin/bash --create-home wtracker

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=wtracker:wtracker . .

# Switch to non-root user
USER wtracker

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production server
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
