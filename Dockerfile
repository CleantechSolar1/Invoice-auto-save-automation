# Dockerfile for Cleantech Invoice Automation
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Kolkata

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code and configuration
COPY src/ ./src/
COPY .env.example ./

# Create data directories for logs and database
RUN mkdir -p logs data

# Default environment pointing database to persistent volume
ENV DATABASE_PATH=/app/data/invoice_automation.db
ENV LOG_FILE_PATH=/app/logs/invoice_automation.log

# Command to run continuously
CMD ["python", "-m", "src.main"]
