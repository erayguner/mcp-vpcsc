# Gemini Enterprise Agent Platform integration

Three optional integrations with the managed Agent Platform, scoped to this
example. The core MCP server and its Cloud Run deployment are unchanged.

| Feature | File | Benefit |
|---|---|---|
| Agent Engine deploy | `deploy_agent_engine.py` | Managed serverless runtime instead of self-hosting the agent on Cloud Run |
| Memory Bank | `memory_bank.py`, `main.py` | Long-term cross-session memory (project, perimeter, workload) without standing up Firestore/Redis |
| Evaluation harness | `evals/` | Tests *agent tool selection* — complements pytest which only tests tool correctness |

## Prerequisites

```bash
pip install 'google-cloud-aiplatform[adk,agent_engines]>=1.95.0'

export GOOGLE_CLOUD_PROJECT=your-project
export GOOGLE_CLOUD_LOCATION=us-central1
export AGENT_ENGINE_STAGING_BUCKET=gs://your-bucket
```

The MCP server must already be deployed to Cloud Run — Agent Engine calls it
over HTTP via `VPCSC_MCP_URL`.

## Agent Engine deployment

```bash
export VPCSC_MCP_URL=https://vpcsc-mcp-xxx.run.app/mcp
uv run python examples/adk-agent/deploy_agent_engine.py deploy
uv run python examples/adk-agent/deploy_agent_engine.py list
```

The script forces `VPCSC_MCP_MODE=remote` because Agent Engine cannot spawn the
MCP server as a subprocess.

## Memory Bank

```bash
# One-time: create the memory store
uv run python examples/adk-agent/memory_bank.py create
# copy the printed resource name

export MEMORY_BANK_AGENT_ENGINE='projects/.../reasoningEngines/...'
```

With `MEMORY_BANK_AGENT_ENGINE` set, `main.py` wires `VertexAiMemoryBankService`
into the FastAPI app; without it, the agent keeps the default in-memory
service. No code changes required to switch.

## Evaluation harness

```bash
# Single command via ADK CLI
adk eval examples/adk-agent/vpcsc_agent examples/adk-agent/evals/eval_sets/basic.evalset.json

# Or through pytest
RUN_ADK_EVALS=1 uv run pytest examples/adk-agent/evals -v
```

Evals hit the live model, so they are skipped by default. Extend
`evals/eval_sets/basic.evalset.json` with more golden tool-call traces as
behaviour changes.
