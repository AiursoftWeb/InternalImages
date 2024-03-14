FROM hub.aiursoft.cn/ubuntu

RUN apt update
RUN apt install -y ttyd sudo wget curl iputils-ping net-tools vim tmux

RUN useradd -p $(openssl passwd -1 demo) demo
RUN usermod -aG sudo demo
RUN echo "demo ALL=(ALL) NOPASSWD:ALL" | sudo tee -a /etc/sudoers.d/demo

# Restore demo's home
RUN mkdir /home/demo
RUN chown demo:demo /home/demo
RUN cp -a /etc/skel/. /home/demo

EXPOSE 7681
ENTRYPOINT ["sh", "-c", "sudo -u demo /usr/bin/ttyd -w /home/demo/ -t disableReconnect=true bash"]
HEALTHCHECK --interval=5s --timeout=3s --retries=3 CMD curl -f http://localhost:7681 || exit 1