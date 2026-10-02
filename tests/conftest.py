import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.llm import ScriptedClient  # noqa: E402
from agent.loop import run_agent  # noqa: E402
from evaluation.checker import load_trace  # noqa: E402


@pytest.fixture
def run(tmp_path):
    """run(script, sender, message, **kw) -> (result, trace, client)"""
    def _run(script, sender="Omar Rashid", message="hi", **kw):
        client = ScriptedClient(script)
        path = tmp_path / "t.jsonl"
        res = run_agent(message, sender, client=client, log_path=str(path), verbose=False, **kw)
        return res, load_trace(path), client
    return _run


@pytest.fixture
def expectations():
    return json.loads((Path(__file__).resolve().parent.parent / "data/expectations.json").read_text(encoding="utf-8"))
