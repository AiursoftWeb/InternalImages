# Iperf3
FROM hub.aiursoft.cn/aiursoft/internalimages/ubuntu
RUN apt update
RUN apt install -y iperf3

EXPOSE 5201

ENTRYPOINT ["sh", "-c", "iperf3 -s"]