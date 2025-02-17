#!/bin/bash
set -e

# Make sure the docker.sock has correct permissions
if [ -S /var/run/docker.sock ]; then
    chown root:docker /var/run/docker.sock
    chmod 660 /var/run/docker.sock
else
    echo "Docker socket not found. Exiting..."
    exit 1
fi


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

echo "Registering runner with token $token with name $HOSTNAME"

# One runner can run 1 tasks at the same time
gitlab-runner register \
    --name $HOSTNAME \
    --non-interactive \
    --url "$gitlab_endpoint" \
    --token $token \
    --executor "shell" \
    --custom_build_dir-enabled  

# Inject `    enabled = true` under `[[runners.custom_build_dir]]` in config.toml
#sed -i 's/\[runners.custom_build_dir\]/\[runners.custom_build_dir\]\n    enabled = true/g' /etc/gitlab-runner/config.toml

#gitlab-runner start
gitlab-runner run --user=gitlab-runner --working-directory=/home/gitlab-runner
