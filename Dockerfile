# AITrader Dockerfile - Environment Only
# This creates a lightweight Python environment without project files
# Project files are mounted at runtime by docker_dev_*.sh scripts
#  agy --conversation=2d5d5148-75e8-4af1-91ea-e57d75c1c4f5 
#  agy --conversation=2e943271-0320-4fba-afea-64e1d4d4ed8b

FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies (including build tools for pandas/numpy)
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    curl \
    gcc \
    g++ \
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    pkg-config \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only pyproject.toml to install dependencies
# Real project files will be mounted at runtime
COPY pyproject.toml .

# Install Python dependencies
# Using pre-built wheels for speed and reliability
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
        numpy \
        pandas \
        python-dateutil \
        pytz \
        tzdata \
        pyyaml \
        pydantic>=2.0 \
        pydantic-settings>=2.0 \
        scipy>=1.10 \
        hmmlearn>=0.3.0 \
        pandas-ta>=0.4.67b0 \
        yfinance>=0.2 \
        streamlit>=1.30 \
        streamlit-extras>=0.3 \
        scikit-learn>=1.3 \
        torch>=2.0 \
        statsmodels>=0.14 \
        xgboost>=2.0 \
        lightgbm>=4.0 \
        arch>=6.2 \
        matplotlib>=3.7 \
        plotly>=5.0 \
        seaborn>=0.12 \
        mplfinance>=0.12 \
        pyarrow>=14.0 \
        pytest>=7.0 \
        pytest-cov>=4.0 \
        pytest-asyncio>=0.23 \
        transformers \
        huggingface-hub \
        httpx \
        fastapi \
        uvicorn \
        websockets


# Create necessary directories (will be populated by mounted volumes)
RUN mkdir -p logs data models reports config src tests scripts dashboards

# Expose ports for Streamlit dashboards
EXPOSE 8501 8502

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src:/app
ENV CONFIG_DIR=/app/config
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_FILE_WATCHER_TYPE=none

# Default command - bash for interactive use
# Actual commands are provided by docker_dev_*.sh scripts
CMD ["/bin/bash"]
