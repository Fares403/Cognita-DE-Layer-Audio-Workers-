# Validation Worker Dockerfile
FROM python:3.11-slim

# Install ffmpeg and ffprobe for audio validation
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "validation.py"]
