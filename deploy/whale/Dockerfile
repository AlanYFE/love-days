FROM node:24-bookworm-slim
ARG DSH_VERSION=0.2.1-rc.4
ARG BILI_COMMIT=8b0009f8ce2ebdc421afcb2e727b19ac18912ec6
RUN apt-get update && apt-get install -y --no-install-recommends git ffmpeg ca-certificates python3 && rm -rf /var/lib/apt/lists/*
RUN npm install -g @deepseek-ai/dsh@${DSH_VERSION}
RUN git init /opt/dsh-bili-whale && cd /opt/dsh-bili-whale && git remote add origin https://github.com/Alterssss/dsh-bili-whale.git && git fetch --depth 1 origin ${BILI_COMMIT} && git checkout --detach FETCH_HEAD && npm ci --omit=dev && rm -rf .git
COPY . /opt/lovedays
USER node
WORKDIR /home/node
ENTRYPOINT ["sh","/opt/lovedays/start.sh"]
