#!/bin/bash
set -e

# Load from environment variables
gitlab_endpoint=${GITLAB_ENDPOINT:-http://gitlab}

echo "Ensure gitlab server $gitlab_endpoint is reachable"
while ! curl -s $gitlab_endpoint/ping; do
    echo "Waiting for gitlab server..."
    sleep 2
done

echo "Reading token from /run/secrets/gitlab-runner-token"
token=$(cat /run/secrets/gitlab-runner-token)

# If token is empty, exit
if [ -z "$token" ]; then
    echo "No token provided."
    exit 1
fi

echo "Registering runner with token $token"

# One runner can run 1 tasks at the same time
gitlab-runner register \
    --non-interactive \
    --url "$gitlab_endpoint" \
    --token $token --executor "shell"

gitlab-runner start
gitlab-runner run --user=gitlab-runner --working-directory=/home/gitlab-runner