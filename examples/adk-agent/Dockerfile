FROM python:3.13-slim

WORKDIR /app

# Install gcloud CLI (needed by the VPC-SC MCP server's gcloud tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
       > /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
       | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && apt-get update && apt-get install -y --no-install-recommends google-cloud-cli \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the VPC-SC MCP server package from the parent project
COPY ../../pyproject.toml /mcp-server/pyproject.toml
COPY ../../src/ /mcp-server/src/
RUN pip install --no-cache-dir /mcp-server

RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app
COPY . .
RUN chown -R appuser:appuser /app

USER appuser
ENV PYTHONUNBUFFERED=1
ENV VPCSC_MCP_MODE=local
ENV VPCSC_MCP_TRANSPORT=stdio

EXPOSE 8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
