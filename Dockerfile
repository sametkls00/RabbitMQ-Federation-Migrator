FROM python:3.9-alpine

WORKDIR /app

RUN apk add --no-cache curl jq bash

# Install Python dependencies
RUN pip install requests pyyaml

# Create scripts directory
RUN mkdir -p /app

# Copy migration scripts
COPY scripts/migrate_federations.py /app/
COPY scripts/check_federations.py /app/

# Set permissions
RUN chmod +x /app/migrate_federations.py /app/check_federations.py

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV OLD_RABBITMQ_PORT=15672
ENV NEW_RABBITMQ_PORT=15672

# Default command
CMD ["python", "/app/migrate_federations.py"]