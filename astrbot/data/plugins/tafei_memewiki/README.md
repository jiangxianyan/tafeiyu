# tafei_memewiki

Native AstrBot integration for the local meme/slang dictionary adapted from the
MIT-licensed [`thawline/dsh-memewiki`](https://github.com/thawline/dsh-memewiki)
project.

- Local SQLite lookup; no chat text is sent for normal queries.
- Matches exact titles, aliases, prefixes, query-contained titles, and selected
  short substrings.
- Injects at most one matched entry into the active persona's prompt.
- Can be enabled independently for Tafei and Dafeiyu.
- Explicit `/tf_meme 词` lookup is available without consuming model tokens.
- Admins can inspect and update the local dictionary.

The dictionary is not committed to the public repository. Its contents come
from `cnmeme.wiki`; see the repository notice and `docs/MEMEWIKI.md`.
