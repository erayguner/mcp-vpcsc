"""Pytest wrapper around the ADK AgentEvaluator.

Skipped unless ADK and google credentials are available — the evals hit the
live model. Run explicitly in CI with `RUN_ADK_EVALS=1`.

Two variants:
  - Flash (default) — fast, cheap, gated by RUN_ADK_EVALS
  - Pro — higher-quality tool-selection check, gated by RUN_ADK_EVALS_PRO

Both Gemini 2.5 variants are in the vertex-genai-offer-2025 SKU group, so
trial credit covers the token spend when active.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

EVAL_SET = Path(__file__).parent / "eval_sets" / "basic.evalset.json"
AGENT_MODULE = "examples.adk-agent.vpcsc_agent"


def _run_eval(model: str) -> None:
    from google.adk.evaluation.agent_evaluator import AgentEvaluator

    os.environ["GEMINI_MODEL"] = model
    AgentEvaluator.evaluate(
        agent_module=AGENT_MODULE,
        eval_dataset_file_path_or_dir=str(EVAL_SET),
        num_runs=1,
    )


@pytest.mark.skipif(
    os.environ.get("RUN_ADK_EVALS") != "1",
    reason="Set RUN_ADK_EVALS=1 to run ADK evaluations against gemini-2.5-flash.",
)
def test_basic_eval_set_flash() -> None:
    _run_eval("gemini-2.5-flash")


@pytest.mark.skipif(
    os.environ.get("RUN_ADK_EVALS_PRO") != "1",
    reason="Set RUN_ADK_EVALS_PRO=1 to run ADK evaluations against gemini-2.5-pro.",
)
def test_basic_eval_set_pro() -> None:
    _run_eval("gemini-2.5-pro")
