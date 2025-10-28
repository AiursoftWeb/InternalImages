FROM hub.aiursoft.com/aiursoft/internalimages/ubuntu:latest
EXPOSE 3389/tcp
ARG USER=test
ARG PasS=1234
ARG X11Forwarding=false

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# 设置时区为 UTC
RUN apt-get update && \
    apt-get install -y tzdata && \
    echo "Etc/UTC" > /etc/timezone && \
    ln -fs /usr/share/zoneinfo/UTC /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata && \
    apt-get clean

# 安装所需软件包
RUN apt-get update && \
    apt-get install -y dbus-x11 xrdp sudo openssl gnome-shell ubuntu-desktop-minimal gnome-console && \
    if [ "$X11Forwarding" = "true" ]; then \
        apt-get install -y openssh-server; \
    fi && \
    apt-get autoremove --purge -y && \
    apt-get clean

# 删除可能存在的重启标记文件
RUN rm -f /run/reboot-required* || true

# 创建用户，并加入 sudo 及 xrdp 所需组
RUN useradd -s /bin/bash -m $USER -p $(openssl passwd "$PasS") && \
    usermod -aG sudo $USER && \
    adduser xrdp ssl-cert

# 配置 locale 及 session 环境变量
RUN echo 'LANG=en_US.UTF-8' >> /etc/default/locale && \
    echo 'export GNOME_SHELL_SESSION_MODE=ubuntu' > /home/$USER/.xsessionrc && \
    echo 'export XDG_CURRENT_DESKTOP=ubuntu:GNOME' >> /home/$USER/.xsessionrc && \
    echo 'export XDG_SESSION_TYPE=x11' >> /home/$USER/.xsessionrc

# 调整 xrdp 配置：
# 1. 启用控制台日志输出
# 2. 强制安全层为 rdp（避免 TLS 握手问题）
# 3. 降低颜色深度到 16 bpp 以提升性能
RUN sed -i 's/#EnableConsole=false/EnableConsole=true/g' /etc/xrdp/xrdp.ini && \
    if grep -q "^security_layer=" /etc/xrdp/xrdp.ini; then \
        sed -i 's/^security_layer=.*/security_layer=rdp/' /etc/xrdp/xrdp.ini; \
    else \
        echo 'security_layer=rdp' >> /etc/xrdp/xrdp.ini; \
    fi && \
    sed -i 's/max_bpp=32/max_bpp=16/g' /etc/xrdp/xrdp.ini

# 禁用 GNOME 动画（提升性能，若无效可忽略）
RUN gsettings set org.gnome.desktop.interface enable-animations false || true

# 如果启用 X11 转发，调整 SSH 配置
RUN if [ "$X11Forwarding" = "true" ]; then \
        sed -i 's/#X11UseLocalhost yes/X11UseLocalhost no/g' /etc/ssh/sshd_config; \
    fi

# 允许用户无密码 sudo
RUN echo "$USER ALL=(ALL) NOPASSWD:ALL" | tee /etc/sudoers.d/$USER

# 启动各项服务并运行 xrdp（保持前台运行）
CMD rm -f /var/run/xrdp/xrdp*.pid >/dev/null 2>&1 && \
    service dbus restart >/dev/null 2>&1 && \
    /usr/lib/systemd/systemd-logind >/dev/null 2>&1 & \
    if [ -f /usr/sbin/sshd ]; then /usr/sbin/sshd; fi && \
    xrdp-sesman --config /etc/xrdp/sesman.ini && \
    xrdp --nodaemon --config /etc/xrdp/xrdp.ini
