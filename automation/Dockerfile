# automation/Dockerfile
#
# Lightweight Python image for running the Devin remediation scripts locally.
# This mirrors exactly what the GitHub Action runs, so local behavior matches CI.
#
# Usage (via docker-compose):
#   docker compose -f automation/docker-compose.yml run create-issues
#   docker compose -f automation/docker-compose.yml run remediate
#   docker compose -f automation/docker-compose.yml run dashboard

FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cached layer — only invalidated if requirements change)
COPY scripts/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the automation scripts
COPY scripts/ ./scripts/

# Create the logs directory (volume mount will overlay this at runtime)
RUN mkdir -p logs

# Default command: show the observability dashboard
CMD ["python", "scripts/dashboard.py"]
