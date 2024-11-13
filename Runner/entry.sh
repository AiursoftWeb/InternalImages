#!/bin/bash
set -e

# Load from environment variables
gitlab_endpoint=${GITLAB_ENDPOINT:-http://gitlab}

echo "Checking if GitLab server $gitlab_endpoint is reachable"
if ! curl -s $gitlab_endpoint; then
    echo "GitLab server is not reachable. Exiting..."
    exit 1
fi

echo "Reading token from /run/secrets/gitlab-runner-token"
token=$(cat /run/secrets/gitlab-runner-token)

# If token is empty, exit
if [ -z "$token" ]; then
    echo "No token provided."
    exit 1
fi

# Copy the config.toml
cp ./config.toml /etc/gitlab-runner/config.toml 

echo "Registering runner with token $token with name $HOSTNAME"

# One runner can run 1 tasks at the same time
gitlab-runner register \
    --name $HOSTNAME \
    --non-interactive \
    --url "$gitlab_endpoint" \
    --token $token --executor "shell"

gitlab-runner start
gitlab-runner run --user=gitlab-runner --working-directory=/home/gitlab-runner --custom_build_dir-enabled=true