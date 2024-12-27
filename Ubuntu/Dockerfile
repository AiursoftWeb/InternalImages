FROM hub.aiursoft.cn/ubuntu:24.10
COPY source.list /etc/apt/sources.list
RUN rm /etc/apt/sources.list.d/*
RUN apt update
RUN apt upgrade -y