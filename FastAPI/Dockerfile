FROM python:3.11-slim

EXPOSE 8001

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# System dependencies for Playwright + PostgreSQL

RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client libpq-dev gcc python3-dev libnss3 libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libgtk-3-0 libxshmfence1 libatk-bridge2.0-0 libdrm2 fonts-liberation  && rm -rf /var/lib/apt/lists/*

# Create app user
RUN adduser -u 5678 --disabled-password --gecos "" appuser
USER appuser

# Set workdir
WORKDIR /app

# Copy requirements first for caching
COPY --chown=appuser:appuser requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Prepare cache dir and install Chromium
RUN mkdir -p /home/appuser/.cache && playwright install --with-deps chromium

# Copy source
COPY --chown=appuser:appuser . /app

# Start app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
