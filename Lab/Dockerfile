FROM hub.aiursoft.cn/ubuntu

RUN apt update
RUN apt install -y ttyd sudo wget curl iputils-ping net-tools vim tmux

RUN useradd -p $(openssl passwd -1 demo) demo
RUN usermod -aG sudo demo

EXPOSE 7681
# sudo -u demo tmux new -d -s shared -c /home/demo/ && sudo -u demo /usr/bin/ttyd -w /home/demo/ tmux attach -t shared
ENTRYPOINT [ "sudo -u demo tmux new -d -s shared -c /home/demo/ && sudo -u demo /usr/bin/ttyd -w /home/demo/ tmux attach -t shared" ]
HEALTHCHECK --interval=5s --timeout=3s --retries=3 CMD curl -f http://localhost:7681 || exit 1