FROM hub.aiursoft.com/aiursoft/internalimages/ubuntu

RUN apt-get update
RUN apt-get install -y ttyd sudo wget curl \
iputils-ping net-tools vim tmux systemd \
apt-transport-https ca-certificates \
software-properties-common w3m git \
python3 python-is-python3 python3-pip \
tree aria2 iperf3 ffmpeg \
unzip zip openssh-server openssh-client \
build-essential bc jq dnsutils lsb-release \
shellcheck pipx dotnet10

RUN useradd -p $(openssl passwd -1 demo) demo
RUN usermod -aG sudo demo
RUN echo "demo ALL=(ALL) NOPASSWD: ALL" | sudo tee -a /etc/sudoers.d/demo

# Restore demo's home
RUN mkdir /home/demo
RUN cp -a /etc/skel/. /home/demo
RUN chown -R demo:demo /home/demo
RUN chmod -R 755 /home/demo

EXPOSE 7681
USER demo
ENTRYPOINT ["sh", "-c", "/usr/bin/ttyd -W -w /home/demo/ /bin/bash"]
HEALTHCHECK --interval=5s --timeout=3s --retries=3 CMD curl -f http://localhost:7681 || exit 1
