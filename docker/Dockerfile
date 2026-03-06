FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

COPY src/ src/
COPY config/ config/

ENV PYTHONPATH=/app/src
ENV CONFIG_DIR=/app/config

CMD ["pytest", "tests", "-v"]
