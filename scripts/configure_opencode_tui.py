"""Add the local AgentRef TUI plugin to OpenCode; preview unless --apply.

Only one exact plugin tuple is managed. Rollback removes that tuple, preserves
other entries, and refuses an edited tuple or ambiguous JSONC configuration.
"""
import argparse
import json
from pathlib import Path

try:
    from scripts.setup_common import atomic_write, local_executable, read_current
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    from setup_common import atomic_write, local_executable, read_current

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / 'integrations/opencode/agentref-tui/tui.mjs'


def update(raw, entry, rollback=False):
    data = json.loads(raw.decode('utf-8-sig')) if raw else {}
    if not isinstance(data, dict) or not isinstance(data.get('plugin', []), list):
        raise ValueError('Expected a JSON object with a plugin array')
    plugins = data.get('plugin', [])
    matching = [value for value in plugins if (value[0] if isinstance(value, list) and value else value) == entry[0]]
    if any(value != entry for value in matching):
        raise ValueError('Existing AgentRef plugin options differ; refusing overwrite')
    if (not rollback and matching) or (rollback and not matching):
        return raw
    data['plugin'] = [value for value in plugins if value != entry] if rollback else [*plugins, entry]
    return (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-dir', type=Path, default=Path.home() / '.config/opencode')
    parser.add_argument('--command', default=str(local_executable(REPO)))
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    path = args.config_dir / 'tui.json'
    jsonc = args.config_dir / 'tui.jsonc'
    if jsonc.exists():
        if path.exists():
            raise ValueError('Both tui.json and tui.jsonc exist; refusing ambiguous edit')
        path = jsonc
    entry = [PLUGIN.as_uri(), {'command': args.command}]
    raw = read_current(path)
    after = update(raw, entry, args.rollback)
    if raw != after and args.apply:
        atomic_write(path, raw, after)
    print(json.dumps({'path': str(path), 'action': 'rollback' if args.rollback else 'install',
                      'changed': raw != after, 'applied': args.apply, 'entry': entry}, ensure_ascii=False))


if __name__ == '__main__':
    main()
