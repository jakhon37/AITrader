# AITrader Dockerfile
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY README.md .
COPY src/ src/
COPY scripts/ scripts/
COPY dashboards/ dashboards/
COPY config/ config/
COPY data/ data/
COPY models/ models/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e ".[live_data,dashboard,ml,viz]"

# Create logs directory
RUN mkdir -p logs

# Expose ports for Streamlit dashboards
EXPOSE 8501 8502

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_FILE_WATCHER_TYPE=none

# Default command (can be overridden)
CMD ["python", "scripts/run_paper.py"]
