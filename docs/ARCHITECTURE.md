# Architecture

## Current

```text
QQ account -> OneBot transport -> AstrBot -> LLM provider
                                     |- group_chat_plus: timing and context
                                     |- tafei_persona: persona and style
                                     |  `- persona_extensions: text plugins
                                     |- tafei_memewiki: local slang lookup
                                     |- tafei_sticker: contextual stickers
                                     |- tafei_memory: group-scoped recall
                                     |- tafei_vision: private-chat image caption
                                     |- tafei_web: opt-in web search
                                     `- local watchdog: AstrBot-only recovery
```

The project-specific code is intentionally kept in AstrBot plugins. AstrBot,
the LLM runtime, and the OneBot transport should be treated as replaceable
infrastructure rather than copied into the repository.

## Feature limits

- Web access only runs for explicit search phrases or a supplied public URL.
- Search keywords are privacy-filtered before leaving the host. URL access
  rejects credentials, private/reserved hosts, non-standard ports, download
  files, unsafe redirects and oversized or attachment responses.
- Search injects at most four short snippets or one short page extract.
- Memory is local and persona/group-scoped. Raw rows are retained for up to
  365 days and 20,000 records; request-time injection remains limited to four
  relevant snippets.
- Startup is serialized by a process lock. The watchdog restarts only AstrBot
  and never automatically recreates NapCat/QQ; bridge failures require one
  manual recovery. NapCat bootstrap attempts are counted and warn after five
  daily attempts without blocking manual recovery.
- Sticker selection uses offline semantic tags and never sends an image to the
  model during normal replies.
- Persona plugins are declarative text packages validated before installation.
  They are scoped by persona, inject at most 3000 characters, and cannot execute
  code in the AstrBot process.
- Group images are captioned before the existing group-chat decision flow.
  Private images are captioned by `tafei_vision` only when an LLM request is
  produced. Captions are content-hash cached and image text is treated as
  untrusted data.
- Stable persona visual cards live separately from cold/hot conversation
  memory. They are scoped by persona and may reference only local,
  user-supplied image assets.
- Yaoguang reads real heat, access count, last-recall time and pinned state from
  the local memory database, then provides a person-scoped star map and clue
  search. Relationship and unfinished-item labels are additional semantic
  filters.

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
