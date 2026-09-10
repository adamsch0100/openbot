FROM python:3.12-slim-bookworm

# Install system dependencies required by Hermes Agent and OpenCode
# build-essential, python3-dev, libffi-dev: needed for Hermes Python package compilation
# libatomic1: needed for Node.js runtime (Hermes installs its own Node)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    build-essential \
    python3-dev \
    libffi-dev \
    libatomic1 \
    && rm -rf /var/lib/apt/lists/*

# Install OpenCode binary (Accept-gated pin — Steward propose)
ENV OPENCODE_VERSION=1.18.30
RUN curl -fsSL https://opencode.ai/install | bash -s -- --version ${OPENCODE_VERSION} --no-modify-path \
    && ln -sf /root/.opencode/bin/opencode /usr/local/bin/opencode \
    && opencode --version

# Install Hermes Agent (Accept-gated pin — Steward propose: v2026.9.7 / v0.21.1)
ENV HERMES_VERSION=v2026.9.7
RUN curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | \
    bash -s -- --skip-setup --skip-browser --non-interactive --branch ${HERMES_VERSION} \
    && hermes --version

# Railway CLI: this board overlays SAA Homes Hermes over SSH. Do not start a second SAA gateway.
ENV RAILWAY_VERSION=5.33.0
RUN curl -fsSL "https://github.com/railwayapp/cli/releases/download/v${RAILWAY_VERSION}/railway-v${RAILWAY_VERSION}-x86_64-unknown-linux-gnu.tar.gz" \
    | tar -xz -C /usr/local/bin railway \
    && railway --version

WORKDIR /app
COPY . /app

ENV PYTHONUNBUFFERED=1
ENV OPENBOT_OPEN_BROWSER=0
ENV OPENBOT_HOST=0.0.0.0
ENV HERMES_HOME=/root/.hermes
ENV OPENBOT_DATA_DIR=/data

# Create data directory and ensure it's writable
# Railway volume will mount over this, but we need it for local/non-volume deploys
RUN mkdir -p /data

EXPOSE 8787

CMD ["python", "bin/openbot"]
