# Unified @ganetref entry

Type `@ganetref`, open its Tab menu and select an agent. The completion inserts
the corresponding `@claude`, `@grok`, `@opencode`, `@antigravity` or `@dsh` text.
Use that entry's native Tab menu to select a session. The current Codex extension
contract has no nested agent item type; this is a text completion bridge.
Desktop focus and consecutive Tab behavior still require a manual UI check.

The catalog refreshes from `codex plugin list --json --marketplace personal`,
reusing successful inventory for up to two seconds during consecutive searches.
Plugin installation or enablement changes appear on the next query after that
window. Failed refreshes report an error instead of returning expired entries.
The catalog excludes uninstalled or disabled entries. This is installation
availability, not a guarantee that each agent's source is currently healthy.
The entry service does not create an index or discover/read session sources.
Existing direct agent menus retain their original behavior.

Install from the repository with:

```powershell
.\.venv\Scripts\python.exe scripts\configure_agent_menu.py --apply
```

The installer registers only `ganetref@personal`; begin a new Codex task after
installation. To disable this entry, remove `ganetref` through Codex's plugin
settings or run `codex plugin remove ganetref@personal`. Individual agent plugins
are independent and remain installed.
