# tafeiyu Voice Plugin

Adds a voice message to eligible replies using the active persona's bound
voice. The binding is read from `config/personas.json` and
`plugin_data/tafei_voice/config.json`; switching persona never reuses the
previous persona's model path.

> This is an unofficial fan project and is not affiliated with the character's
> official team. Voice weights and reference audio are not distributed with
> this plugin. Users must provide resources they are authorized to use.

- Local GPT-SoVITS: configure a persona-specific manifest and TTS config
- External FeiyuVoice: `POST /v1/speech`, poll `/v1/jobs/{id}`, then download
  the validated WAV from `/v1/jobs/{id}/audio`
- Default auto probability: `0.15`
- Default maximum spoken text: `60` Chinese characters
- Owner private chat uses voice deterministically for replies up to 200
  characters; the QQ admin/deployment IDs are merged into the owner list
- Voice references: normal / cute / happy / annoyed / soft
- Explicit voice requests such as "发语音" or "说一句" force a voice reply
- Cached samples are isolated by persona, model, reference audio and style

Admin commands:

- `/tf_voice 文字` — generate and send a test voice
- `/tf_voice_p 0.15` — set automatic voice probability
- `/tf_voice_on` / `/tf_voice_off`

See the repository's `NOTICE.md` for attribution and third-party asset rules.
