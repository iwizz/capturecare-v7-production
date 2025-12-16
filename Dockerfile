FROM python:3.11-slim

# Force rebuild - Import fixes + DB migration for attachments 2025-12-16
ENV BUILD_VERSION=20251216_v5_db_migration_complete

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY . /app

# Set Python path to include the app directory
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8080

# Run with gunicorn (as a package)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120", "--keep-alive", "2", "--max-requests", "1000", "--max-requests-jitter", "100", "--preload", "capturecare.web_dashboard:app"]
