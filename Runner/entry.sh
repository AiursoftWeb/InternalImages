token=$(cat /run/secrets/gitlab-runner-token)

# One runner can run 3 tasks at the same time
gitlab-runner register \
    --non-interactive \
    --url "https://gitlab.aiursoft.cn/" \
    --token $token

gitlab-runner start
gitlab-runner run --user=gitlab-runner --working-directory=/home/gitlab-runner