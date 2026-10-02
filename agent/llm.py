"""
ScriptedClient: a stand-in for anthropic.Anthropic() that replays a fixed script.

It exists so the LOOP (stop logic, dedup, guardrails, tracing) can be tested
deterministically, offline and for free. Traces produced with it are NOT model
behaviour and every trace header says model="scripted". Real model runs use
anthropic.Anthropic() (see loop.run_agent).

A script is a list of turns. A turn is {"text": str?, "calls": [(tool, args), ...]}.
A turn with no calls ends the model's turn (stop_reason "end_turn").
"""

from types import SimpleNamespace


class ScriptedClient:
    def __init__(self, turns):
        self._turns = list(turns)
        self._i = 0
        self.messages = self  # so client.messages.create(...) works
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if self._i >= len(self._turns):
            raise AssertionError("ScriptedClient: script exhausted (loop asked for more turns than scripted)")
        turn = self._turns[self._i]
        self._i += 1
        content = []
        if turn.get("text"):
            content.append(SimpleNamespace(type="text", text=turn["text"]))
        for n, (name, args) in enumerate(turn.get("calls", []), 1):
            content.append(SimpleNamespace(type="tool_use", id=f"toolu_{self._i}_{n}", name=name, input=args))
        stop = "tool_use" if turn.get("calls") else "end_turn"
        return SimpleNamespace(
            content=content, stop_reason=stop,
            usage=SimpleNamespace(input_tokens=0, output_tokens=0),
        )
