# Iperf3
FROM hub.aiursoft.com/aiursoft/internalimages/ubuntu
RUN apt-get update
RUN apt-get install -y iperf3

EXPOSE 5201

ENTRYPOINT ["sh", "-c", "iperf3 -s"]