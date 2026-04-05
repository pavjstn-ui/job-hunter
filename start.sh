#!/bin/bash

# Job Hunter Agent startup script
# Designed to be run from cron

# Change to the project directory
cd /root/projects/job-hunter || {
    echo "ERROR: Could not change to /root/projects/job-hunter" >&2
    exit 1
}

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "Virtual environment activated"
fi

# Load environment variables from .env file
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
    echo "Environment variables loaded from .env"
fi

# Start the agent with nohup
echo "$(date): Starting Job Hunter Agent via start.sh" >> agent.log
nohup python -u agent.py >> agent.log 2>&1 &

# Get the PID
PID=$!
echo "Agent started with PID: $PID"
echo "$(date): Agent started with PID $PID" >> agent.log
