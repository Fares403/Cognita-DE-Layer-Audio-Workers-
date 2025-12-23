#!/bin/sh
# Wait for MinIO to be ready
sleep 5
mc alias set myminio http://minio:9000 minioadmin minioadmin123
mc mb -p myminio/raw-audio-meetings || true