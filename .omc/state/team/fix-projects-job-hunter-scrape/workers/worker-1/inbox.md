## REQUIRED: Task Lifecycle Commands
You MUST run these commands. Do NOT skip any step.

1. Claim your task:
   omc team api claim-task --input '{"team_name":"fix-projects-job-hunter-scrape","task_id":"1","worker":"worker-1"}' --json
   Save the claim_token from the response.
2. Do the work described below.
3. On completion (use claim_token from step 1):
   omc team api transition-task-status --input '{"team_name":"fix-projects-job-hunter-scrape","task_id":"1","from":"in_progress","to":"completed","claim_token":"<claim_token>"}' --json
4. On failure (use claim_token from step 1):
   omc team api transition-task-status --input '{"team_name":"fix-projects-job-hunter-scrape","task_id":"1","from":"in_progress","to":"failed","claim_token":"<claim_token>"}' --json
5. ACK/progress replies are not a stop signal. Keep executing your assigned or next feasible work until the task is actually complete or failed, then transition and exit.

## Task Assignment
Task ID: 1
Worker: worker-1
Subject: Fix ~/projects/job-hunter/scraper/profesia.py - getting 301 redirect. Add follow

Fix ~/projects/job-hunter/scraper/profesia.py - getting 301 redirect. Add follow_redirects=True to httpx client

REMINDER: You MUST run transition-task-status before exiting. Do NOT write done.json or edit task files directly.