#!/bin/bash

# Setup cron jobs for Job Hunter Agent

# Make start.sh executable
chmod +x /root/projects/job-hunter/start.sh

# Get current crontab and add our entries
crontab -l > /tmp/current_cron 2>/dev/null || true

# Check if entries already exist
if ! grep -q "@reboot.*start.sh" /tmp/current_cron 2>/dev/null; then
    echo "@reboot sleep 30 && bash /root/projects/job-hunter/start.sh" >> /tmp/current_cron
fi

if ! grep -q "pgrep -f agent.py.*start.sh" /tmp/current_cron 2>/dev/null; then
    echo "*/30 * * * * pgrep -f agent.py || bash /root/projects/job-hunter/start.sh" >> /tmp/current_cron
fi

# Install the new crontab
crontab /tmp/current_cron

# Show the installed crontab
echo "Current crontab:"
crontab -l

# Clean up
rm -f /tmp/current_cron
