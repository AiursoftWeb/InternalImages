#!/bin/sh
set -e

cp -r /datapacks/* /app/world/datapacks/

tmux new-session -d -s mc \
    'java -XX:+UseG1GC -Xms4G -Xmx12G -jar /app/papermc.jar --nojline --nogui > /var/log/mc/mc.log 2>&1'

bash /app/init-commands.sh &

exec tail -f /var/log/mc/mc.log
