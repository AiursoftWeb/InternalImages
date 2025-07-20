#!/bin/bash
set -e

echo "Starting GitLab Runner registration script..."

# Make sure the docker.sock has correct permissions
if [ -S /var/run/docker.sock ]; then
    # We need that socket to create new job containers
    chown root:docker /var/run/docker.sock
    chmod 660 /var/run/docker.sock
else
    echo "Docker socket not found. Exiting..."
    exit 1
fi

# JOB_CONTAINER_IMAGE
job_container_image=${JOB_CONTAINER_IMAGE}
if [ -z "$job_container_image" ]; then
    echo "JOB_CONTAINER_IMAGE is not set. Exiting..."
    exit 1
fi

job_docker_to_use_socket=${JOB_DOCKER_TO_USE_SOCKET}
if [ -z "$job_docker_to_use_socket" ]; then
    echo "JOB_DOCKER_TO_USE_SOCKET is not set. Exiting..."
    exit 1
fi

job_container_in_network=${JOB_CONTAINER_IN_NETWORK}
if [ -z "$job_container_in_network" ]; then
    echo "JOB_CONTAINER_IN_NETWORK is not set. Exiting..."
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

# Use host docker socket to start job docker containers
# However, in job docker containers, if the job needs to run docker commands, it should use the docker socket in the job container. Configured by JOB_DOCKER_TO_USE_SOCKET
# For example, if JOB_DOCKER_TO_USE_SOCKET is set to /var/run/docker.sock, then the job container will use the host's docker socket.
# For example, if JOB_DOCKER_TO_USE_SOCKET is set to tcp://docker:2375, then the job container will use the docker socket in the dind container.
gitlab-runner register \
    --name $HOSTNAME \
    --non-interactive \
    --url "$gitlab_endpoint" \
    --token $token \
    --executor "docker" \
    --env "DOCKER_HOST=$job_docker_to_use_socket" \
    --env "DOCKER_TLS_CERTDIR=" \
    --docker-image "$job_container_image" \
    --docker-network-mode "$job_container_in_network" \
    --docker-volumes "/certs/client" \
    --custom_build_dir-enabled=true

#gitlab-runner start
gitlab-runner run --user=gitlab-runner --working-directory=/home/gitlab-runner
