FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Official, unmodified Claude Code binary. Its account state lives in /data.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://claude.ai/install.sh -o /tmp/claude-install.sh \
    && bash /tmp/claude-install.sh 2.1.293 \
    && install -m 0755 /root/.local/bin/claude /usr/local/bin/claude \
    && claude --version \
    && rm -f /tmp/claude-install.sh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
ENV CLAUDE_CONFIG_DIR=/data/claude-code DISABLE_AUTOUPDATER=1

COPY hubnex ./hubnex
COPY web ./web
COPY config ./config
COPY integration ./integration

EXPOSE 8765
VOLUME ["/app/data"]
CMD ["python", "-m", "hubnex.main"]
