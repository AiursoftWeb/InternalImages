FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu
WORKDIR /
RUN apt update
RUN apt install -y apt-mirror git unzip wget cron

# Install a patched version of apt-mirror
RUN wget https://github.com/Stifler6996/apt-mirror/archive/refs/heads/master.zip
RUN unzip master.zip
RUN mv ./apt-mirror-master/apt-mirror /usr/bin/apt-mirror
RUN rm -rf ./apt-mirror-master
RUN chown root:root /usr/bin/apt-mirror
RUN chmod 755 /usr/bin/apt-mirror

# Set the configuration file for apt-mirror
RUN mkdir -p /etc/apt
RUN echo "set base_path /var/spool/apt-mirror" > /etc/apt/mirror.list
RUN echo "set nthreads 20" >> /etc/apt/mirror.list
RUN echo "set _tilde 0" >> /etc/apt/mirror.list

RUN echo "deb http://mirrors.zju.edu.cn/ubuntu/ noble main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb http://mirrors.zju.edu.cn/ubuntu/ noble-updates main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb http://mirrors.zju.edu.cn/ubuntu/ noble-backports main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb http://mirrors.zju.edu.cn/ubuntu/ noble-security main restricted universe multiverse" >> /etc/apt/mirror.list

RUN echo "deb [arch=i386] http://mirrors.zju.edu.cn/ubuntu/ noble main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb [arch=i386] http://mirrors.zju.edu.cn/ubuntu/ noble-updates main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb [arch=i386] http://mirrors.zju.edu.cn/ubuntu/ noble-backports main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb [arch=i386] http://mirrors.zju.edu.cn/ubuntu/ noble-security main restricted universe multiverse" >> /etc/apt/mirror.list

RUN echo "deb http://mirrors.zju.edu.cn/ubuntu/ jammy main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb http://mirrors.zju.edu.cn/ubuntu/ jammy-updates main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb http://mirrors.zju.edu.cn/ubuntu/ jammy-backports main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb http://mirrors.zju.edu.cn/ubuntu/ jammy-security main restricted universe multiverse" >> /etc/apt/mirror.list

RUN echo "deb [arch=i386] http://mirrors.zju.edu.cn/ubuntu/ jammy main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb [arch=i386] http://mirrors.zju.edu.cn/ubuntu/ jammy-updates main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb [arch=i386] http://mirrors.zju.edu.cn/ubuntu/ jammy-backports main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb [arch=i386] http://mirrors.zju.edu.cn/ubuntu/ jammy-security main restricted universe multiverse" >> /etc/apt/mirror.list

# RUN echo "deb http://mirrors.zju.edu.cn/ubuntu/ focal main restricted universe multiverse" >> /etc/apt/mirror.list
# RUN echo "deb http://mirrors.zju.edu.cn/ubuntu/ focal-updates main restricted universe multiverse" >> /etc/apt/mirror.list
# RUN echo "deb http://mirrors.zju.edu.cn/ubuntu/ focal-backports main restricted universe multiverse" >> /etc/apt/mirror.list
# RUN echo "deb http://mirrors.zju.edu.cn/ubuntu/ focal-security main restricted universe multiverse" >> /etc/apt/mirror.list

RUN echo "deb-amd64 http://ppa.launchpad.net/nextcloud-devs/client/ubuntu noble main" >> /etc/apt/mirror.list
RUN echo "deb-amd64 http://ppa.launchpad.net/mozillateam/ppa/ubuntu noble main" >> /etc/apt/mirror.list
#RUN echo "deb-amd64 http://ppa.launchpad.net/saiarcot895/chromium-beta/ubuntu noble main" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://ppa.launchpad.net/nextcloud-devs/client/ubuntu noble main" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://ppa.launchpad.net/mozillateam/ppa/ubuntu noble main" >> /etc/apt/mirror.list
#RUN echo "deb-i386 http://ppa.launchpad.net/saiarcot895/chromium-beta/ubuntu noble main" >> /etc/apt/mirror.list

RUN echo "deb-amd64 http://ppa.launchpad.net/nextcloud-devs/client/ubuntu jammy main" >> /etc/apt/mirror.list
RUN echo "deb-amd64 http://ppa.launchpad.net/mozillateam/ppa/ubuntu jammy main" >> /etc/apt/mirror.list
#RUN echo "deb-amd64 http://ppa.launchpad.net/saiarcot895/chromium-beta/ubuntu jammy main" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://ppa.launchpad.net/nextcloud-devs/client/ubuntu jammy main" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://ppa.launchpad.net/mozillateam/ppa/ubuntu jammy main" >> /etc/apt/mirror.list
#RUN echo "deb-i386 http://ppa.launchpad.net/saiarcot895/chromium-beta/ubuntu jammy main" >> /etc/apt/mirror.list

RUN echo "clean http://mirrors.zju.edu.cn/ubuntu/" >> /etc/apt/mirror.list

RUN touch /var/spool/apt-mirror/var/postmirror.sh && chmod +x /var/spool/apt-mirror/var/postmirror.sh

VOLUME /var/spool/apt-mirror

# Register a crontab job to run apt-mirror every day
RUN crontab -l | { cat; echo "0 5 * * * /usr/bin/apt-mirror"; } | crontab -

# Run this job at the beginning with verbose output
ENTRYPOINT ["cron", "-f", "-L 15"]