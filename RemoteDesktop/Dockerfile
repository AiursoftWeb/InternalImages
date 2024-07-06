FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu:latest
EXPOSE 3389/tcp
ARG USER=test
ARG PASS=1234
ARG X11Forwarding=false

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Install tzdata and set the timezone to UTC
RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    apt-get install -y tzdata && \
    echo "Etc/UTC" > /etc/timezone && \
    ln -fs /usr/share/zoneinfo/UTC /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    apt-get install -y dbus-x11 xrdp sudo openssl gnome-shell ubuntu-desktop-minimal gnome-console && \
    [ $X11Forwarding = 'true' ] && apt-get install -y openssh-server; \
    apt-get autoremove --purge; \
    apt-get clean;

# Remove the reboot required file
RUN rm /run/reboot-required* || true

# Create a user and add it to the sudo group
RUN useradd -s /bin/bash -m $USER -p $(openssl passwd "$PASS"); \
    usermod -aG sudo $USER; \
    adduser xrdp ssl-cert;

# Setting the required environment variables
RUN echo 'LANG=en_US.UTF-8' >> /etc/default/locale; \
    echo 'export GNOME_SHELL_SESSION_MODE=ubuntu' > /home/$USER/.xsessionrc; \
    echo 'export XDG_CURRENT_DESKTOP=ubuntu:GNOME' >> /home/$USER/.xsessionrc; \
    echo 'export XDG_SESSION_TYPE=x11' >> /home/$USER/.xsessionrc;

# Enabling log to the stdout
RUN sed -i "s/#EnableConsole=false/EnableConsole=true/g" /etc/xrdp/xrdp.ini;

# Disabling system animations and reducing the image quality to improve the performance
RUN sed -i 's/max_bpp=32/max_bpp=16/g' /etc/xrdp/xrdp.ini; \
    gsettings set org.gnome.desktop.interface enable-animations true;

# Listening on wildcard address for X forwarding
RUN [ $X11Forwarding = 'true' ] && \
        sed -i 's/#X11UseLocalhost yes/X11UseLocalhost no/g' /etc/ssh/sshd_config || :;

# Adding the user to the sudoers file
RUN echo "$USER ALL=(ALL) NOPASSWD:ALL" | tee -a /etc/sudoers.d/$USER

CMD rm -f /var/run/xrdp/xrdp*.pid >/dev/null 2>&1; \
    service dbus restart >/dev/null 2>&1; \
    /usr/lib/systemd/systemd-logind >/dev/null 2>&1 & \
    [ -f /usr/sbin/sshd ] && /usr/sbin/sshd; \
    xrdp-sesman --config /etc/xrdp/sesman.ini; \
    xrdp --nodaemon --config /etc/xrdp/xrdp.ini
