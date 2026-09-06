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

# Install OpenCode binary
# The install script detects platform and downloads the appropriate binary to ~/.opencode/bin
RUN curl -fsSL https://opencode.ai/install | bash -s -- --no-modify-path \
    && ln -sf /root/.opencode/bin/opencode /usr/local/bin/opencode \
    && opencode --version

# Install Hermes Agent using official installer
# Running as root in Docker triggers FHS layout: code at /usr/local/lib/hermes-agent,
# binary at /usr/local/bin/hermes (created by installer), data at /root/.hermes
RUN curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | \
    bash -s -- --skip-setup --skip-browser --non-interactive \
    && hermes --version

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
