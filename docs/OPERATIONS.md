# Operations

## Start and stop

- Start: `启动塔菲.bat`
- Stop: `关闭塔菲.bat`
- Status: `python .bot_runtime/bot_manager.py status`

Do not use the one-off scripts at the repository root. They are intentionally
excluded from Git because they were created during migration and debugging.

## Live configuration

Copy `config/tafei.settings.example.json` to `config/tafei.settings.json`, then
set the real group IDs and run:

```powershell
python scripts/apply_review_fixes.py
```

The live settings file is ignored by Git.

## Secrets

- Provider credentials live in AstrBot's live `cmd_config.json`.
- Local integration credentials live in `.secrets/tafei.env.json`.
- Both paths are ignored by Git and have restricted Windows ACLs.
- Never include `astrbot/data`, `.secrets`, session databases, or logs in a
  public release.

## Persona

Runtime sources are:

- `astrbot/data/personas/tafei.md`
- `astrbot/data/plugin_data/tafei_persona/style.txt`
- `astrbot/data/plugin_data/tafei_persona/glossary.txt`

Regenerate the readable snapshot with:

```powershell
python scripts/export_persona.py
```

## Validation

Run:

```powershell
python scripts/check_project.py
```

This checks Python syntax, sticker probability behavior, removed hard-coded
tokens, and overly broad one-character sticker keywords.
