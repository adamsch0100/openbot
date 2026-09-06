FROM python:3.12-slim-bookworm

# Install system dependencies required by Hermes Agent and OpenCode
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install OpenCode binary
# The install script detects platform and downloads the appropriate binary to ~/.opencode/bin
RUN curl -fsSL https://opencode.ai/install | bash -s -- --no-modify-path \
    && ln -sf /root/.opencode/bin/opencode /usr/local/bin/opencode \
    && opencode --version

# Install Hermes Agent using official installer
# Use --skip-setup to avoid interactive prompts, --skip-browser to skip Playwright in container
# The installer clones to ~/.hermes/hermes-agent and creates a venv
RUN curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | \
    bash -s -- --skip-setup --skip-browser --non-interactive \
    && ln -sf /root/.hermes/hermes-agent/venv/bin/hermes /usr/local/bin/hermes \
    && hermes --version

WORKDIR /app
COPY . /app

ENV PYTHONUNBUFFERED=1
ENV OPENBOT_OPEN_BROWSER=0
ENV OPENBOT_HOST=0.0.0.0
ENV HERMES_HOME=/root/.hermes

EXPOSE 8787

CMD ["python", "bin/openbot"]
