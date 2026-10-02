# Lighthouse in a box: Debian's Chromium + a pinned Lighthouse. Run it inside the app container's
# network namespace (--network container:<app>) so the app is http://localhost, a secure context.
FROM node:22-bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends chromium \
 && rm -rf /var/lib/apt/lists/* \
 && npm install -g lighthouse@12.8.2 \
 && npm cache clean --force
ENV CHROME_PATH=/usr/bin/chromium
USER node
WORKDIR /home/node
ENTRYPOINT ["lighthouse", "--chrome-flags=--headless=new --no-sandbox --disable-dev-shm-usage", "--quiet"]
