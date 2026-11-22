# 瑶光记忆星图

`瑶光` is tafeiyu's local memory-atlas interface. It reproduces the general
interaction pattern of recent companion-memory dashboards without copying
third-party source code or assets.

## Current features

- Dark star-map canvas centred on the active persona core.
- Separate visual layers for fixed facts, hot memories, cold memories,
  relationship cues, speaking habits, and unfinished matters.
- Persona selector for Tafei and Dafeiyu.
- Free-text clue search across memory text, sender/source, session and date.
- Click a star to inspect its original text, real heat, recall count, source
  ID, importance, date, and owning group.
- Copy the selected memory text to the clipboard.
- Read-only UI; it does not silently rewrite or delete memory records.

## Hot/cold state

The memory database stores one state row for every original memory:

- `heat`: accumulated from creation importance and successful recalls;
- `access_count`: how often the memory was actually injected through a cue;
- `last_accessed`: the most recent successful recall;
- `pinned`: durable facts created by explicit remember commands.

Heat decays when a memory is not recalled. A recent recall or sufficient
effective heat keeps it hot; fixed facts stay fixed; older unrecalled entries
become cold. Cold rows remain searchable, but are only injected when the
current message contains a matching cue.

Yaoguang reads this state directly. Relationship and unfinished-item categories
are additional semantic filters and do not replace the underlying hot/cold
state.

## Privacy

The window reads the local SQLite memory database and persona style files.
It does not upload memory, call a model, or make network requests.

## Source code

`launcher/yaoguang_memory.py`
