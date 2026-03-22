FROM python:3.13-slim

# Install gcloud CLI for tools that call gcloud commands
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
       > /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
       | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && apt-get update && apt-get install -y --no-install-recommends google-cloud-cli \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir .

# Run as non-root user — principle of least privilege
RUN adduser --disabled-password --gecos "" --uid 1001 appuser \
    && chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1
ENV VPCSC_MCP_TRANSPORT=streamable-http
ENV PORT=8080

EXPOSE 8080

CMD ["python", "-m", "vpcsc_mcp.server"]
