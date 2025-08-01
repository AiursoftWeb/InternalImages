FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu
WORKDIR /
RUN apt-get update
RUN apt-get install -y apt-mirror git unzip wget cron

# Install a patched version of apt-mirror
RUN wget https://gist.aiursoft.cn/anduin/57a393ed8ed343c9bc8a9ae7a30f61e5/raw/HEAD/apt-mirror -O ./apt-mirror
RUN chown root:root ./apt-mirror && chmod 755 ./apt-mirror
RUN mv ./apt-mirror /usr/bin/apt-mirror
RUN rm -rf ./apt-mirror-master
RUN chown root:root /usr/bin/apt-mirror
RUN chmod 755 /usr/bin/apt-mirror

# Set the configuration file for apt-mirror
RUN mkdir -p /etc/apt
RUN echo "set base_path /var/spool/apt-mirror" > /etc/apt/mirror.list
RUN echo "set nthreads 20" >> /etc/apt/mirror.list
RUN echo "set _tilde 0" >> /etc/apt/mirror.list

# questing
RUN echo "deb http://mirrors.ustc.edu.cn/ubuntu/ questing main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb http://mirrors.ustc.edu.cn/ubuntu/ questing-updates main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb http://mirrors.ustc.edu.cn/ubuntu/ questing-backports main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb http://mirrors.ustc.edu.cn/ubuntu/ questing-security main restricted universe multiverse" >> /etc/apt/mirror.list

# questing i386
RUN echo "deb-i386 http://mirrors.ustc.edu.cn/ubuntu/ questing main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://mirrors.ustc.edu.cn/ubuntu/ questing-updates main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://mirrors.ustc.edu.cn/ubuntu/ questing-backports main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://mirrors.ustc.edu.cn/ubuntu/ questing-security main restricted universe multiverse" >> /etc/apt/mirror.list

# plucky
RUN echo "deb http://mirrors.ustc.edu.cn/ubuntu/ plucky main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb http://mirrors.ustc.edu.cn/ubuntu/ plucky-updates main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb http://mirrors.ustc.edu.cn/ubuntu/ plucky-backports main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb http://mirrors.ustc.edu.cn/ubuntu/ plucky-security main restricted universe multiverse" >> /etc/apt/mirror.list

# plucky i386
RUN echo "deb-i386 http://mirrors.ustc.edu.cn/ubuntu/ plucky main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://mirrors.ustc.edu.cn/ubuntu/ plucky-updates main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://mirrors.ustc.edu.cn/ubuntu/ plucky-backports main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://mirrors.ustc.edu.cn/ubuntu/ plucky-security main restricted universe multiverse" >> /etc/apt/mirror.list

# oracular
RUN echo "deb http://mirrors.ustc.edu.cn/ubuntu/ oracular main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb http://mirrors.ustc.edu.cn/ubuntu/ oracular-updates main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb http://mirrors.ustc.edu.cn/ubuntu/ oracular-backports main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb http://mirrors.ustc.edu.cn/ubuntu/ oracular-security main restricted universe multiverse" >> /etc/apt/mirror.list

# oracular i386
RUN echo "deb-i386 http://mirrors.ustc.edu.cn/ubuntu/ oracular main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://mirrors.ustc.edu.cn/ubuntu/ oracular-updates main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://mirrors.ustc.edu.cn/ubuntu/ oracular-backports main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://mirrors.ustc.edu.cn/ubuntu/ oracular-security main restricted universe multiverse" >> /etc/apt/mirror.list

# noble
RUN echo "deb http://mirrors.ustc.edu.cn/ubuntu/ noble main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb http://mirrors.ustc.edu.cn/ubuntu/ noble-updates main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb http://mirrors.ustc.edu.cn/ubuntu/ noble-backports main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb http://mirrors.ustc.edu.cn/ubuntu/ noble-security main restricted universe multiverse" >> /etc/apt/mirror.list

# noble i386
RUN echo "deb-i386 http://mirrors.ustc.edu.cn/ubuntu/ noble main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://mirrors.ustc.edu.cn/ubuntu/ noble-updates main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://mirrors.ustc.edu.cn/ubuntu/ noble-backports main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://mirrors.ustc.edu.cn/ubuntu/ noble-security main restricted universe multiverse" >> /etc/apt/mirror.list

# jammy
RUN echo "deb http://mirrors.ustc.edu.cn/ubuntu/ jammy main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb http://mirrors.ustc.edu.cn/ubuntu/ jammy-updates main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb http://mirrors.ustc.edu.cn/ubuntu/ jammy-backports main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb http://mirrors.ustc.edu.cn/ubuntu/ jammy-security main restricted universe multiverse" >> /etc/apt/mirror.list

# Add some ppa

# plucky
RUN echo "deb-amd64 http://ppa.launchpad.net/nextcloud-devs/client/ubuntu plucky main" >> /etc/apt/mirror.list
RUN echo "deb-amd64 http://ppa.launchpad.net/mozillateam/ppa/ubuntu plucky main" >> /etc/apt/mirror.list
RUN echo "deb-amd64 http://ppa.launchpad.net/graphics-drivers/ppa/ubuntu plucky main" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://ppa.launchpad.net/nextcloud-devs/client/ubuntu plucky main" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://ppa.launchpad.net/mozillateam/ppa/ubuntu plucky main" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://ppa.launchpad.net/graphics-drivers/ppa/ubuntu plucky main" >> /etc/apt/mirror.list

# oracular
RUN echo "deb-amd64 http://ppa.launchpad.net/nextcloud-devs/client/ubuntu oracular main" >> /etc/apt/mirror.list
RUN echo "deb-amd64 http://ppa.launchpad.net/mozillateam/ppa/ubuntu oracular main" >> /etc/apt/mirror.list
RUN echo "deb-amd64 http://ppa.launchpad.net/graphics-drivers/ppa/ubuntu oracular main" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://ppa.launchpad.net/nextcloud-devs/client/ubuntu oracular main" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://ppa.launchpad.net/mozillateam/ppa/ubuntu oracular main" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://ppa.launchpad.net/graphics-drivers/ppa/ubuntu oracular main" >> /etc/apt/mirror.list

# noble
RUN echo "deb-amd64 http://ppa.launchpad.net/nextcloud-devs/client/ubuntu noble main" >> /etc/apt/mirror.list
RUN echo "deb-amd64 http://ppa.launchpad.net/mozillateam/ppa/ubuntu noble main" >> /etc/apt/mirror.list
RUN echo "deb-amd64 http://ppa.launchpad.net/graphics-drivers/ppa/ubuntu noble main" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://ppa.launchpad.net/nextcloud-devs/client/ubuntu noble main" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://ppa.launchpad.net/mozillateam/ppa/ubuntu noble main" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://ppa.launchpad.net/graphics-drivers/ppa/ubuntu noble main" >> /etc/apt/mirror.list

# jammy
RUN echo "deb-amd64 http://ppa.launchpad.net/nextcloud-devs/client/ubuntu jammy main" >> /etc/apt/mirror.list
RUN echo "deb-amd64 http://ppa.launchpad.net/mozillateam/ppa/ubuntu jammy main" >> /etc/apt/mirror.list
RUN echo "deb-amd64 http://ppa.launchpad.net/graphics-drivers/ppa/ubuntu jammy main" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://ppa.launchpad.net/nextcloud-devs/client/ubuntu jammy main" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://ppa.launchpad.net/mozillateam/ppa/ubuntu jammy main" >> /etc/apt/mirror.list
RUN echo "deb-i386 http://ppa.launchpad.net/graphics-drivers/ppa/ubuntu jammy main" >> /etc/apt/mirror.list

RUN echo "clean http://mirrors.ustc.edu.cn/ubuntu/" >> /etc/apt/mirror.list

RUN touch /var/spool/apt-mirror/var/postmirror.sh && chmod +x /var/spool/apt-mirror/var/postmirror.sh

VOLUME /var/spool/apt-mirror

# Register a crontab job to run apt-mirror every day. (5 times retry.)
#RUN crontab -l | { cat; echo "0 5 * * * /usr/bin/apt-mirror"; } | crontab -
RUN crontab -l | { cat; echo "0 5 * * * /usr/bin/apt-mirror; /usr/bin/apt-mirror; /usr/bin/apt-mirror; /usr/bin/apt-mirror; /usr/bin/apt-mirror"; } | crontab -

# Run this job at the beginning with verbose output
ENTRYPOINT ["cron", "-f", "-L 15"]