# tafeiyu

`tafeiyu`（塔菲鱼）is an unofficial QQ AI companion built on AstrBot and OneBot.

The source is licensed under **AGPL-3.0**; see `LICENSE`. The desktop client is
a Windows control center with a left navigation rail for runtime status,
one-click persona switching, voice bindings, the visual memory atlas, sticker
asset management, persona plugins, setup, and diagnostics.

## Unofficial fan project and voice assets

This is an unofficial fan-made companion project. It is not affiliated with,
authorized by, or endorsed by 永雏塔菲, her official team, or the rights holders.

Part of the personality and speaking-style guidance is adapted from the
MIT-licensed [ace-taffy-skill](https://github.com/ly-xxx/ace-taffy-skill)
project. The original project and its contributors retain their respective
copyrights.

Voice model weights, reference audio, generated voice samples, and other
third-party character assets are **not included** in this repository, its
installer, or its release packages. The current voice resources do not have a
confirmed redistribution license. Users must obtain and use voice resources
that they are legally permitted to use.

Any project community group is for installation discussion and user-assisted
discovery only. It does not host or endorse unauthorized copies. The group
number or invitation link, when available, will be published on the release
page.

See [NOTICE.md](NOTICE.md) for the full attribution and asset policy.

中文说明：本项目是非官方粉丝作品，人格与说话方式的一部分参考了
MIT 许可的 `ace-taffy-skill`。语音模型权重和参考音频未取得明确的再分发
许可，因此不会随公开安装包提供。请自行取得并仅使用你有权使用的声线资源；
项目交流群仅用于安装讨论和合法来源交流，不会托管未经授权的文件，群号或
加群链接将在 Release 页面公布。

## First run

Install the desktop launcher dependencies first:

```powershell
python -m pip install -r requirements-launcher.txt
```

The setup wizard now detects the local AstrBot executable and NapCat Shell,
records their paths in the ignored deployment state, creates separate text and
vision providers, and writes the owner QQ into the image-reply allowlist.

The client opens directly into the main dashboard after setup. Imported
persona Markdown files appear under “人格切换” and receive independent memory,
visual identity, plugin state, and optional voice binding.

On the first launch, `tafeiyu` opens a five-step setup wizard:

1. Configure an OpenAI-compatible text model, vision model, and API key.
2. Set the bot QQ and owner QQ, then log in by QR code after setup.
3. Optionally import GPT-SoVITS weights and one reference audio sample.
4. Configure group allowlists and blocklists.
5. Save the configuration, restart the services, and show the login QR code.

The first-run wizard does not ask users to rename the default role: `tafei`
remains the initial persona. Additional built-in or imported personas are
selected from the client after setup. Users can open the wizard again from the
launcher to change the model, QQ account, voice pack, or group lists. API keys
remain in the local AstrBot configuration and are not written to public project
files.

## Personas and memory star map

The built-in persona catalog contains:

- `tafei` — the default Taffy persona.
- `dafeiyu` — the DeepSeek Xiaojingyu / “大肥鱼” group-chat persona.

Persona metadata lives in `config/personas.json`, while the individual persona
cards remain Markdown files under `astrbot/data/personas/`. Additional personas
can be added without changing the installer.

Each persona has its own voice binding and memory scope. Switching persona also
switches the selected voice binding; a missing or disabled voice never falls
back to the previous persona’s voice. Message recall and rolling summaries are
stored under persona-scoped session keys as well.

Memory recall now records heat, recall count, last-access time and a pinned
state. Explicitly remembered facts stay fixed; recently recalled memories stay
hot; unrecalled entries cool down but remain searchable and are only injected
when the current message provides a matching cue.

The launcher includes a local “瑶光” Memory Star Map. It reads the active persona’s
speaking rules and only that persona’s records in the local `tafei_memory`
database, then displays habits, relationships, topics, and conversation
memories as an interactive star map.
The current lightweight renderer is built into the client and does not upload
memory content anywhere. For a future 3D renderer, the MIT-licensed
[3d-force-graph](https://github.com/vasturiano/3d-force-graph) project is a
compatible reference.

See [docs/YAOGUANG.md](docs/YAOGUANG.md) for the current Yaoguang dashboard,
memory-layer classification, privacy behavior, and implementation limits.

Opt-in web search sanitizes queries before external transmission and applies
private-network, port, download-file, redirect, domain, response-size and
content-type checks to public links.

## Private-chat vision and persona visual identity

Group-chat images are processed by the group-chat extension. Private-chat
images are handled by the separate `tafei_vision` plugin, which describes each
image with `deepseek/deepseek-vision` before the active persona replies. Image
descriptions are cached by content hash, and text found inside an image is
treated as untrusted visual content rather than an instruction.

For the configured group-chat owner IDs, an ordinary image now bypasses the
ambient-chat probability and “stay silent” decision, so sending a picture
directly produces a visual reply. Existing per-minute reply-density limits
still apply.

Each persona also has a separate, stable visual identity card under
`astrbot/data/persona_visuals/`. The launcher’s “人格形象” page can store
appearance, hair, outfit, colors, motifs, recognition notes, and user-supplied
authorized reference images. Visual identity is deliberately kept out of
ordinary cold/hot conversation memory, so chat cannot silently rewrite it and
Taffy and Dafeiyu never share the same visual card.

See [docs/VISION_AND_VISUALS.md](docs/VISION_AND_VISUALS.md) for configuration,
recognized markers, privacy behavior, and image-import details.

## Sticker replies and image battles

`tafei_sticker` keeps the original behavior of occasionally appending a
context-matched sticker after a text reply. It now also detects incoming QQ
stickers and can replace the generated text with one relevant sticker, creating
a bounded sticker duel. The default limit is three rounds within 180 seconds,
with an 85% reply probability and a short anti-retry cooldown.

See [docs/STICKERS.md](docs/STICKERS.md) for commands and configuration. The
meme-wiki plugin remains a text dictionary and does not choose or send images.

The client’s “表情包库” is a visual asset browser: thumbnails appear on the
left and the selected sticker’s keywords, emotions, intent, tone, and usage
notes appear in editable fields on the right. Newly imported files are scanned
once when AstrBot starts and tagged by the configured vision provider. Existing
manual tags are never overwritten by that scan.

## Persona-bound voice center

The “人格与声线” page shows the voice binding for every persona:

- Taffy uses a locally imported GPT-SoVITS V2 voice pack.
- Dafeiyu connects to a separately deployed FeiyuVoice HTTP service.

The page provides official project, model, and deployment-guide buttons. It
does not bundle third-party weights, reference audio, or copied service code.
Large-language-model chat continues in text-only mode when the selected
persona’s voice is unavailable.

See [docs/VOICE_PACKS.md](docs/VOICE_PACKS.md) for installation, licensing,
port-conflict, and service-connection details.

## Persona-scoped plugins

The launcher includes a “人格插件” page where users can install a local
`.tafeiplugin` package and enable it independently for each persona. The first
version intentionally supports declarative prompt extensions only:

- persistent prompt guidance;
- optional keyword-triggered prompt guidance;
- per-persona enable and disable state;
- install-time package validation and a simple uninstall flow.

Plugin packages cannot contain Python, executables, DLLs, scripts, shortcuts,
temporary symlinks, encrypted archives, or traversal paths. Plugin content
cannot execute code in the AstrBot process and is explicitly placed below core
persona and safety instructions.

See [docs/PERSONA_PLUGINS.md](docs/PERSONA_PLUGINS.md) for the package format.
An installable example source directory is available at
`examples/persona_plugins/weather_hint`.

The plugin center also contains a native “梗百科” extension adapted from the
MIT-licensed `thawline/dsh-memewiki` project. It provides local meme/slang
lookup and injects at most one matched dictionary entry into the active
persona. The 6792-entry SQLite dictionary is downloaded separately because its
contents are attributed to `cnmeme.wiki`; it is not included in this public
repository.

See [docs/MEMEWIKI.md](docs/MEMEWIKI.md) for matching behavior, commands, data
storage, updates, and licensing.

## Layout

- `astrbot/data/plugins/tafei_persona`: persona and speaking-rule injection
- `astrbot/data/plugins/tafei_vision`: private-chat image description
- `astrbot/data/plugins/tafei_sticker`: context-aware sticker replies
- `astrbot/data/plugins/tafei_memory`: local, group-scoped conversation recall
- `astrbot/data/plugins/tafei_voice`: persona-bound local or HTTP speech output
- `astrbot/data/plugins/tafei_web`: opt-in search and public-link reading
- `.bot_runtime`: service manager and watchdog
- `launcher`: the Windows one-click launcher
- `launcher/sticker_library.py`: visual sticker asset browser and tag editor
- `persona_manager_core.py`: local Markdown persona import
- `launcher/yaoguang_memory.py`: dark memory atlas and clue search UI
- `persona_extensions`: shared validation, installation, and prompt loading
- `memewiki_core`: local meme dictionary lookup and validated updates
- `astrbot/data/plugins/tafei_memewiki`: native AstrBot dictionary integration
- `docs/PERSONA_PLUGINS.md`: persona-plugin package format and security rules
- `config/personas.json`: persona catalog and one-to-one voice bindings
- `tafei_role.md`: human-readable consolidated persona reference
- `docs/OPERATIONS.md`: safe operating and validation workflow
- `docs/ARCHITECTURE.md`: current runtime and AuraBot evaluation notes
- `scripts/build_offline_package.py`: split offline package builder
- `.github/workflows`: CI and tagged release workflows

## Important

Live configuration, API keys, generated logs, downloaded runtimes, and account
session data are intentionally excluded from Git. Use a dedicated QQ account
and keep deployment-specific secrets outside the repository.

## Safety

Start or stop the local deployment through the desktop shortcuts
`启动塔菲鱼` and `关闭塔菲鱼`. Do not run ad-hoc scripts from the downloads
directory.

Offline email notifications have been removed. If only AstrBot stops, the
watchdog may restart AstrBot without touching NapCat/QQ. If the QQ bridge is
disconnected, the watchdog only notifies and waits for one manual recovery.
Startup APIs use a process lock, and legacy launch scripts are kept under
`legacy_launchers` so only one public entry remains. NapCat/QQ bootstrap is
counted per local day and warns after five attempts, while manual recovery
remains available.
