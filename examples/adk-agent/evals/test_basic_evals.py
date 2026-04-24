"""Pytest wrapper around the ADK AgentEvaluator.

Skipped unless ADK and google credentials are available — the eval hits the
live model. Run explicitly in CI with `RUN_ADK_EVALS=1`.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

EVAL_SET = Path(__file__).parent / "eval_sets" / "basic.evalset.json"
AGENT_MODULE = "examples.adk-agent.vpcsc_agent"


@pytest.mark.skipif(
    os.environ.get("RUN_ADK_EVALS") != "1",
    reason="Set RUN_ADK_EVALS=1 to run ADK evaluations against the live model.",
)
def test_basic_eval_set() -> None:
    from google.adk.evaluation.agent_evaluator import AgentEvaluator

    AgentEvaluator.evaluate(
        agent_module=AGENT_MODULE,
        eval_dataset_file_path_or_dir=str(EVAL_SET),
        num_runs=1,
    )
