# Tafei QQ Bot

Personal QQ AI companion built on AstrBot and OneBot.

## Layout

- `astrbot/data/plugins/tafei_persona`: persona and speaking-rule injection
- `astrbot/data/plugins/tafei_sticker`: context-aware sticker replies
- `astrbot/data/plugins/tafei_memory`: local, group-scoped conversation recall
- `astrbot/data/plugins/tafei_web`: opt-in search and public-link reading
- `.bot_runtime`: service manager and watchdog
- `tafei_role.md`: human-readable consolidated persona reference
- `docs/OPERATIONS.md`: safe operating and validation workflow
- `docs/ARCHITECTURE.md`: current runtime and AuraBot evaluation notes

## Important

Live configuration, API keys, generated logs, downloaded runtimes, and account
session data are intentionally excluded from Git. Use a dedicated QQ account
and keep deployment-specific secrets outside the repository.

## Safety

Start or stop the local deployment through `启动塔菲.bat` and
`关闭塔菲.bat`. Do not run ad-hoc scripts from the downloads directory.

Offline email notifications have been removed. A failed automatic reconnect
now stops repeated attempts and waits for manual login.
