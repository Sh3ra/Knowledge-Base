#!/usr/bin/env bash
# Orchestration script for PDF Ingestor & Semantic Search API
# Usage: ./orchestrate.sh --action start | terminate

set -e

ACTION=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --action)
            ACTION="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [[ -z "$ACTION" ]]; then
    echo "Usage: ./orchestrate.sh --action start | terminate"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed or not in PATH"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo "Error: Docker Compose is not available"
    exit 1
fi

case "$ACTION" in
    start)
        echo "Starting services..."
        docker compose up -d --build
        echo "Services started. API available at http://localhost:8000"
        echo "Docs at http://localhost:8000/docs"
        ;;
    terminate)
        echo "Stopping and removing services..."
        docker compose down -v
        echo "Services terminated."
        ;;
    *)
        echo "Error: Invalid action '$ACTION'. Use 'start' or 'terminate'."
        exit 1
        ;;
esac
