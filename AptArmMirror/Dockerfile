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

# plucky — only ARM binaries (arm64)
RUN echo "deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports plucky          main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports plucky-updates  main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports plucky-backports main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports plucky-security  main restricted universe multiverse" >> /etc/apt/mirror.list

# oracular — only ARM binaries (arm64)
RUN echo "deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports oracular          main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports oracular-updates  main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports oracular-backports main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports oracular-security  main restricted universe multiverse" >> /etc/apt/mirror.list

# noble — only ARM binaries (arm64)
RUN echo "deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports noble          main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports noble-updates  main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports noble-backports main restricted universe multiverse" >> /etc/apt/mirror.list
RUN echo "deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports noble-security  main restricted universe multiverse" >> /etc/apt/mirror.list

RUN echo "clean http://ports.ubuntu.com/ubuntu-ports" >> /etc/apt/mirror.list

RUN touch /var/spool/apt-mirror/var/postmirror.sh
RUN chmod +x /var/spool/apt-mirror/var/postmirror.sh

VOLUME /var/spool/apt-mirror

# Register a crontab job to run apt-mirror every day. (5 times retry.)
#RUN crontab -l | { cat; echo "0 5 * * * /usr/bin/apt-mirror"; } | crontab -
RUN crontab -l | { cat; echo "0 5 * * * /usr/bin/apt-mirror || /usr/bin/apt-mirror || /usr/bin/apt-mirror || /usr/bin/apt-mirror || /usr/bin/apt-mirror"; } | crontab -

# Run this job at the beginning with verbose output
ENTRYPOINT ["cron", "-f", "-L", "15"]
