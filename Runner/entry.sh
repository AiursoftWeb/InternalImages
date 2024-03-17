token=$(cat /run/secrets/gitlab-runner-token)
gitlab-runner register \
    --non-interactive \
    --url "https://gitlab.aiursoft.cn/" \
    --registration-token $token \
    --executor "shell" \
    --description "aiursoft-runner-docker" \
    --tag-list "ubuntu,shared,runner,docker" \
    --run-untagged="true" \
    --locked="false"

fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.conf && sudo sysctl -p
gitlab-runner start
gitlab-runner verify
gitlab-runner run --user=gitlab-runner --working-directory=/home/gitlab-runner