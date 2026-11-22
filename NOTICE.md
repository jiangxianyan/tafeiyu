# Notice and Third-Party Attributions

## Unofficial fan project

`tafeiyu` is an unofficial fan-made AI companion project. It is not
affiliated with, authorized by, sponsored by, or endorsed by 永雏塔菲, her
official team, the platform operators, or any related rights holder.

The character name and references to publicly known settings are used to
describe an unofficial fan adaptation. They do not imply official status or
endorsement.

The project source is distributed under the GNU Affero General Public License
version 3.0. See `LICENSE`. This choice also keeps our distribution of the
AGPL-licensed Group Chat Plus plugin and its local modifications compliant.

## Personality attribution

Part of the personality and speaking-style guidance in this project is adapted
from:

- Project: `ace-taffy-skill`
- Repository: https://github.com/ly-xxx/ace-taffy-skill
- Declared license: MIT

The upstream project and its contributors retain copyright in their respective
contributions. This project's attribution does not claim ownership of, or
exclusive rights to, the upstream project's material.

## Voice-model and audio policy

This repository and its public release packages do not contain:

- GPT-SoVITS model weights
- reference audio
- generated voice samples
- copied character artwork, Live2D models, music, or stickers

The current voice resources do not have a confirmed redistribution license.
Publicly accessible files are not necessarily licensed for redistribution.
Users must obtain voice models and reference audio from sources they are legally
entitled to use and must comply with applicable platform rules, personality
rights, voice rights, and other third-party rights.

The project does not host unauthorized copies and does not grant permission to
redistribute third-party voice resources. A community group, if one is created,
is intended for installation discussion and user-assisted discovery of lawful
sources. Its group number or invitation link will be published on the project
release page when available.

The optional Dafeiyu voice integration only calls a separately deployed
HTTP service. It does not bundle or copy the upstream
`astrbot_plugin_feiyu_voice` source, FeiyuVoice model weights, or reference
audio. The upstream repository's `NOTICE.md` does not assign a blanket
redistribution license to its locally authored source, and its model materials
carry separate character-asset and training-authorization constraints. Users
must follow the upstream project's deployment and licensing terms.

### 中文说明

本项目是非官方粉丝作品，人格和说话方式的一部分参考自 MIT 许可的
`ace-taffy-skill`。当前语音权重和参考音频没有明确再分发许可，因此不会
包含在公开仓库、安装器或 Release 安装包中。

用户可以自行取得并仅使用自己有权使用的声线资源。项目交流群只用于安装
讨论和合法来源交流，不托管或认可未经授权的副本；具体群号或加群链接以
项目 Release 页面公布的信息为准。

## Secrets and user data

Do not include any of the following in public commits or release packages:

- API keys or access tokens
- QQ or NapCat login sessions
- chat databases or user conversation exports
- runtime logs
- deployment-specific configuration containing credentials

## Third-party software

This project uses or integrates with third-party software including AstrBot,
NapCat, GPT-SoVITS, and AstrBot plugins. Each component remains subject to its
own license and terms. Public distributions must include the relevant copyright
notices and license texts where required.

The bundled, modified copy of
[`Him666233/astrbot_plugin_group_chat_plus`](https://github.com/Him666233/astrbot_plugin_group_chat_plus)
is licensed under AGPL-3.0. Its original `LICENSE`, metadata and README remain
inside the plugin directory. Local modifications include image-triggered reply
controls and compatibility changes. The complete corresponding source is
distributed in this repository.

The optional 3D memory-graph upgrade path references
[`3d-force-graph`](https://github.com/vasturiano/3d-force-graph), copyright
Vasco Asturiano, under the MIT License. The current built-in Tk star map does
not bundle that library.

## Meme-wiki adaptation

The native meme-wiki integration is adapted from
[`thawline/dsh-memewiki`](https://github.com/thawline/dsh-memewiki), which is
licensed under the MIT License, copyright (c) 2026 dsh-memewiki contributors.
The original design was inspired by the AstrBot plugin
`astrbot_plugin_memewiki` by in1t1a1.

The SQLite dictionary is not included in this repository, installer, or public
release package. Its data is attributed by the upstream project to
`cnmeme.wiki` and the original plugin's bundled dataset. Users download it
explicitly into an ignored local runtime directory from the official upstream
public distribution.

The upstream MIT license text is included in
[`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md).
