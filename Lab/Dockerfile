FROM hub.aiursoft.cn/ubuntu

RUN apt update
RUN apt install -y ttyd sudo wget curl iputils-ping net-tools vim tmux systemd apt-transport-https ca-certificates software-properties-common w3m git python3 python-is-python3 python3-pip
RUN hostnamectl set-hostname lab

RUN useradd -p $(openssl passwd -1 demo) demo
RUN usermod -aG sudo demo
RUN echo "demo ALL=(ALL) NOPASSWD:ALL" | sudo tee -a /etc/sudoers.d/demo

# Restore demo's home
RUN mkdir /home/demo
RUN chown -R demo:demo /home/demo
RUN chmod -R 755 /home/demo
RUN cp -a /etc/skel/. /home/demo

EXPOSE 7681
ENTRYPOINT ["sh", "-c", "sudo -u demo /usr/bin/ttyd -w /home/demo/ -t bash"]
HEALTHCHECK --interval=5s --timeout=3s --retries=3 CMD curl -f http://localhost:7681 || exit 1