# Architecture

## Current

```text
QQ account -> OneBot transport -> AstrBot -> LLM provider
                                     |- group_chat_plus: timing and context
                                     |- tafei_persona: persona and style
                                     |- tafei_sticker: contextual stickers
                                     `- local watchdog: process recovery
```

The project-specific code is intentionally kept in AstrBot plugins. AstrBot,
the LLM runtime, and the OneBot transport should be treated as replaceable
infrastructure rather than copied into the repository.

## Evaluation candidate

AuraBot 1.2.0 with SnowLuma is a separate candidate, not yet the active runtime:

- Stronger fit for long-term memory, voice, mood, desktop pet, and modular QQ
  behavior.
- Newer and less battle-tested than AstrBot.
- SnowLuma is an independent third-party QQ integration with a source-available
  non-commercial license and the same account-risk class as other unofficial
  integrations.

Evaluate it in an isolated directory with a separate QQ account before any
migration.
