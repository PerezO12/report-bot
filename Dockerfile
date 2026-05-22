# Multi-stage Dockerfile for BotDaily and BotAdmin
# Build: docker build --target main -t botdaily:main .
#        docker build --target admin -t botdaily:admin .

# Base stage with all dependencies
FROM python:3.12-slim AS base

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY bot/ bot/
COPY admin_bot/ admin_bot/
COPY flows/ flows/
COPY main.py admin_main.py ./

# Create non-root user
RUN useradd -m -u 1000 botuser
USER botuser

# Main bot target
FROM base AS main
CMD ["python", "-u", "main.py"]

# Admin bot target
FROM base AS admin
CMD ["python", "-u", "admin_main.py"]
