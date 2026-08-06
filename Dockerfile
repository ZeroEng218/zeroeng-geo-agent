FROM python:3.11-slim

# The Claude Agent SDK is a Python wrapper around the Claude Code CLI
# (a Node.js binary). Both Node and the CLI must be present in the image --
# the SDK shells out to the CLI at runtime, authenticating purely via the
# ANTHROPIC_API_KEY environment variable (no interactive login needed).
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g @anthropic-ai/claude-code && \
    apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY geo_agent.py server.py ./

EXPOSE 8000

# Railway injects $PORT; fall back to 8000 for local runs. Shell form (not
# exec-array form) so the ${PORT:-8000} expansion actually happens.
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}
