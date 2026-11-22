# Operations

## Start and stop

- Start: `启动塔菲.bat`
- Stop: `关闭塔菲.bat`
- Status: `python .bot_runtime/bot_manager.py status`

Do not use the one-off scripts at the repository root. They are intentionally
excluded from Git because they were created during migration and debugging.

## Live configuration

Install launcher dependencies with:

```powershell
python -m pip install -r requirements-launcher.txt
```

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

## Added features

- `tafei_web`: searches only on explicit requests such as “搜一下” or when the
  user supplies a public link. Set `tavily_api_key` in `.secrets/tafei.env.json`
  to use Tavily; otherwise the plugin uses Bing RSS snippets. Queries are
  stripped of account IDs, phone numbers, email addresses, CQ codes and
  secret-like strings before external transmission. Optional
  `web_allowed_domains` and `web_blocked_domains` arrays in the same secrets
  file restrict result and user-supplied URLs by hostname.
- `tafei_memory`: stores group-scoped text in a local SQLite trigram index for
  365 days with hot/cold heat, recall count and last-access state. Admin
  commands are `/tf_remember`, `/tf_forget`, and `/tf_memory_status`.
- `tafei_sticker`: selects from the curated local library using offline emotion,
  intent, and tone tags.

## QQ reconnect policy

- Use only the desktop `启动塔菲鱼` entry. Historical debug launchers are kept
  under `legacy_launchers` and must not be used for daily startup.
- Concurrent launcher runs are blocked by a local startup lock.
- If the AstrBot dashboard stops, the watchdog may restart AstrBot only.
- If AstrBot is online but NapCat/QQ is disconnected, the watchdog only
  notifies; it does not restart the QQ bridge automatically.
- NapCat/QQ bootstrap attempts are counted per local day. After five attempts
  the client warns about risk-control cooldown but still allows manual recovery.

## Validation

Run:

```powershell
python scripts/check_project.py
```

This checks Python syntax, sticker probability behavior, removed hard-coded
tokens, and overly broad one-character sticker keywords.
