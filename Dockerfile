FROM python:3.11-alpine

WORKDIR /app

# Install dependencies (curl, jq for scripts)
RUN apk add --no-cache \
    curl \
    jq

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY config_generator.py .
COPY entrypoint.sh .
COPY fetch_key.sh .
RUN chmod +x entrypoint.sh fetch_key.sh

# Make fetch-nord-key available in path easier (optional, or just use /app/fetch_key.sh)
RUN ln -s /app/fetch_key.sh /usr/local/bin/fetch-nord-key

# Default environment variables
ENV XRAY_PORT=10000

ENTRYPOINT ["/app/entrypoint.sh"]
