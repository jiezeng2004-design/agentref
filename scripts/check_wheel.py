"""Build and smoke-test a wheel outside the checkout using synthetic data only.

Build dependencies may be downloaded by pip. Installation uses the resulting
local wheelhouse in a fresh venv; no host configuration or personal sessions are
read. Temporary build, wheelhouse, index and environment are removed on exit.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import venv

REPO = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(args, cwd, env, *, input=None):
    result = subprocess.run([str(arg) for arg in args], cwd=cwd, env=env,
                            input=input, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=300)
    # Do not echo pip output: configured indexes may contain authentication data.
    require(result.returncode == 0,
            f"Wheel check subprocess failed (exit {result.returncode}); command: {Path(str(args[0])).name}")
    return result.stdout


def check():
    with tempfile.TemporaryDirectory(prefix="agentref-wheel-") as temporary:
        root = Path(temporary).resolve()
        require(not root.is_relative_to(REPO), "Wheel check must run outside checkout")
        env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        source = root / "source"
        source.mkdir()
        for name in ("pyproject.toml", "README.md", "LICENSE"):
            shutil.copyfile(REPO / name, source / name)
        shutil.copytree(REPO / "agentref", source / "agentref",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        wheelhouse = root / "wheels"
        print("Building wheel and dependency wheels in temporary directory...", flush=True)
        run([sys.executable, "-m", "pip", "wheel", "--wheel-dir", wheelhouse, source], root, env)
        wheels = list(wheelhouse.glob("agentref-*.whl"))
        require(len(wheels) == 1, "Expected exactly one AgentRef wheel")
        environment = root / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        bindir = environment / ("Scripts" if os.name == "nt" else "bin")
        python = bindir / ("python.exe" if os.name == "nt" else "python")
        cli = bindir / ("agentref.exe" if os.name == "nt" else "agentref")
        run([python, "-I", "-m", "pip", "install", "--no-index", "--find-links", wheelhouse, wheels[0]], root, env)
        probe = """
import hashlib, json
from pathlib import Path
import agentref
from agentref.sources import supported_formats
package = Path(agentref.__file__).resolve().parent
assets = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
          for p in (package / 'assets').iterdir() if p.is_file()}
print(json.dumps({'package': str(package), 'version': agentref.__version__,
                  'assets': assets, 'formats': supported_formats()}))
"""
        installed = json.loads(run([python, "-I", "-c", probe], root, env))
        require(Path(installed["package"]).is_relative_to(environment), "Import did not use installed wheel")
        expected_assets = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in (source / "agentref/assets").iterdir() if p.is_file()}
        require(installed["assets"] == expected_assets, "Wheel assets missing or changed")
        require(run([cli, "--version"], root, env).strip() == installed["version"], "CLI version mismatch")
        sessions = root / "fixtures"
        sessions.mkdir()
        fixture = sessions / "synthetic.jsonl"
        records = [
            {"type": "session_meta", "payload": {"id": "wheel-fixture"}},
            {"type": "response_item", "payload": {"type": "message", "role": "user",
             "content": [{"type": "input_text", "text": "Synthetic wheel check 你好"}]}},
        ]
        fixture.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        before = fixture.read_bytes()
        prefix = [cli, "--data-dir", root / "index", "--codex-root", sessions]
        doctor = json.loads(run([*prefix, "doctor"], root, env))
        require(set(doctor["roots"]) == {"codex"}, "Unexpected personal source enabled")
        require(doctor["supportedFormats"] == installed["formats"], "Doctor catalog mismatch")
        require(doctor["database"] == "ok" and doctor["parser"] == "ok", "Doctor failed")
        rows = json.loads(run([*prefix, "sessions", "--json"], root, env))
        require(len(rows) == 1 and rows[0]["sessionId"] == "wheel-fixture", "Fixture discovery failed")

        def rpc(requests):
            text = "".join(json.dumps({"jsonrpc": "2.0", "id": n, "method": method,
                                      "params": params}) + "\n"
                           for n, (method, params) in enumerate(requests, 1))
            replies = [json.loads(line) for line in run([*prefix, "mcp"], root, env, input=text).splitlines()]
            require(len(replies) == len(requests) and all("result" in r for r in replies), "MCP request failed")
            return [r["result"] for r in replies]

        initialize = ("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                     "clientInfo": {"name": "wheel-check", "version": "1"}})
        handshake, inventory = rpc([initialize, ("resources/list", {})])
        require(handshake["serverInfo"]["version"] == installed["version"], "MCP version mismatch")
        resources = inventory["resources"]
        require(len(resources) == 1, "MCP fixture inventory mismatch")
        _, context = rpc([initialize, ("resources/read", {"uri": resources[0]["uri"]})])
        require("Synthetic wheel check 你好" in json.dumps(context, ensure_ascii=False), "MCP context missing fixture")
        require(fixture.read_bytes() == before, "Source fixture was modified")
        print(json.dumps({"wheel": wheels[0].name, "installedOutsideCheckout": True,
                          "assetsVerified": len(expected_assets), "cli": "passed", "mcp": "passed",
                          "syntheticOnly": True, "modelCalled": False}))


if __name__ == "__main__":
    check()
