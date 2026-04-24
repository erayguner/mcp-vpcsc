FROM python:3.14-slim

# Ensure pipefail so broken pipes surface as build failures (hadolint DL4006).
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install uv and gcloud CLI
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Pull Debian security patches first to close HIGH/CRITICAL CVEs surfaced by
# Trivy on every fresh scan. -y + -o Dpkg to avoid interactive prompts.
RUN apt-get update \
    && apt-get upgrade -y \
       -o Dpkg::Options::="--force-confdef" \
       -o Dpkg::Options::="--force-confold" \
    && apt-get install -y --no-install-recommends \
       curl \
       gnupg \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
       > /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
       | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && apt-get update && apt-get install -y --no-install-recommends google-cloud-cli \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src/ src/

RUN uv sync --frozen --no-dev --no-editable

# Run as non-root user — principle of least privilege
RUN adduser --disabled-password --gecos "" --uid 1001 appuser \
    && chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1
ENV VPCSC_MCP_TRANSPORT=streamable-http
ENV PORT=8080

EXPOSE 8080

CMD ["uv", "run", "python", "-m", "vpcsc_mcp.server"]
