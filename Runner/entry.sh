token=$(cat /run/secrets/gitlab-runner-token)

# If token is empty, exit
if [ -z "$token" ]; then
    echo "No token provided."
    exit 1
fi

echo "Registering runner with token $token"

# One runner can run 3 tasks at the same time
gitlab-runner register \
    --non-interactive \
    --url "https://gitlab.aiursoft.cn/" \
    --token $token --executor "shell"

gitlab-runner start
gitlab-runner run --user=gitlab-runner --working-directory=/home/gitlab-runner