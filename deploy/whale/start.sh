#!/bin/sh
set -eu
umask 077
mkdir -p /home/node/.dsh /home/node/.bili-ai
if [ ! -f /home/node/.dsh/bili-whale.config.json ]; then
  cp /opt/lovedays/bili-whale.config.json /home/node/.dsh/bili-whale.config.json
fi
if [ ! -f /home/node/.dsh/lovedays-plugins-v1 ]; then
  dsh plugin --profile web add link:/opt/dsh-bili-whale
  dsh plugin --profile web add link:/opt/lovedays
  touch /home/node/.dsh/lovedays-plugins-v1
fi
exec dsh --profile web --host 0.0.0.0 --port 3080 --no-open
