"""Deterministic fixture demo, NOT a real model or native @ UI acceptance test."""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agentref.adapters import ClaudeAdapter, CodexAdapter
from agentref.index import Index
from agentref.handoff import build_context

repo = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="agentref-demo-") as temp:
    root = Path(temp)
    workspace = root / "workspace"
    workspace.mkdir()
    (workspace / "registry.py").write_text("REGISTRY = {}\n", encoding="utf-8")
    for agent, adapter_type in (("codex", CodexAdapter), ("claude", ClaudeAdapter)):
        sources = root / agent
        sources.mkdir()
        source = sources / "interrupted.jsonl"
        data = (repo / "tests/fixtures" / (agent + "-normal.jsonl")).read_bytes()
        if agent == "codex":
            event = {"type": "event_msg", "payload": {"type": "turn_aborted"}}
        else:
            event = {"type": "system", "subtype": "interrupt"}
        source.write_bytes(data + json.dumps(event).encode() + b'\n{"partial":')
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        index = Index(root / (agent + "-index"), [adapter_type([sources])])
        try:
            index.refresh()
            session = index.read(index.sessions()[0])
            context = build_context(session, workspace)
            assert "rollback" in context and "incomplete trailing" in context
            assert hashlib.sha256(source.read_bytes()).hexdigest() == before
            assert index.refresh()["bytesRead"] == 0
            print(agent + " -> other agent: fixture context PASS; source unchanged; warm index reads 0 transcript bytes")
        finally:
            index.close()
print("Synthetic bidirectional integration only. Real agents and native @ picker NOT exercised.")
