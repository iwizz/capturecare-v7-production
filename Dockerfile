FROM python:3.11-slim

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

# Run with gunicorn (from the capturecare directory)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120", "--keep-alive", "2", "--max-requests", "1000", "--max-requests-jitter", "100", "--preload", "--chdir", "capturecare", "web_dashboard:app"]
