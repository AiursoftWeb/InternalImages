FROM hub.aiursoft.cn/ubuntu

# GitLab Runner.
RUN apt update
RUN apt install -y gitlab-runner dotnet8 nodejs libgdiplus build-essential

# Token will be placed at /run/secrets/gitlab-runner-token
RUN token=$(cat /run/secrets/gitlab-runner-token)
RUN gitlab-runner register \
    --non-interactive \
    --url "https://gitlab.aiursoft.cn/" \
    --registration-token $token \
    --executor "shell" \
    --description "aiursoft-runner-docker" \
    --tag-list "ubuntu,shared,runner,docker" \
    --run-untagged="true" \
    --locked="false"

RUN fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.conf && sudo sysctl -p
RUN gitlab-runner start
RUN gitlab-runner verify
ENTRYPOINT ["gitlab-runner", "run", "--user=gitlab-runner", "--working-directory=/home/gitlab-runner"]