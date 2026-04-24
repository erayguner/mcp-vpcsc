# VPC-SC Agent Evaluation Harness

Evaluates whether the ADK agent correctly invokes MCP tools for common VPC-SC
scenarios. Uses the [ADK evaluation framework](https://google.github.io/adk-docs/evaluate/)
which is the same engine behind Vertex AI's managed Evaluation Service.

## Running

Eval sets live under `evals/eval_sets/` in the ADK schema. Run via pytest:

```bash
uv run pytest examples/adk-agent/evals -v
```

Or via the ADK CLI:

```bash
adk eval examples/adk-agent/vpcsc_agent examples/adk-agent/evals/eval_sets/basic.evalset.json
```

## What the default set covers

- `list_perimeters` — agent invokes the read-only list tool, no write attempts
- `generate_perimeter_terraform` — agent picks the Terraform generator, not the gcloud writer
- `troubleshoot_denial` — agent calls the violation analyser before suggesting a fix

Add cases by appending to `eval_sets/basic.evalset.json` following the ADK
eval schema.
