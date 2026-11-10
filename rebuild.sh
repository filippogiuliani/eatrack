#!/bin/sh
# Rebuild and restart eaTrack. Data stays in ./eaTrack_data (mounted on /app/data).
set -e
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  echo "The .env file is missing: copy .env.example to .env and configure it." >&2
  exit 1
fi
sudo docker build -t eatrack .
sudo docker rm -f eatrack 2>/dev/null || true
sudo docker run -d --restart unless-stopped -p 3000:3000 --env-file .env \
  -v "$(pwd)/eaTrack_data:/app/data" --name eatrack eatrack
echo "eaTrack started on http://localhost:3000"
