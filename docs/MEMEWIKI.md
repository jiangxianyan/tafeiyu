# 梗百科：本地梗与黑话词库

塔菲鱼的“梗百科（内置）”移植自 MIT 许可的
[`thawline/dsh-memewiki`](https://github.com/thawline/dsh-memewiki) 项目。
原项目是 DeepSeek Harness 的 JavaScript 插件；塔菲鱼按其匹配和注入设计，
独立实现了 Python/AstrBot 版本。

## 功能

- 本地 SQLite 词库，当前为 6792 条梗和黑话。
- 用户问“XX 是什么梗”或直接发送一个明确裸词时，自动查询。
- 命中后只向当前人格注入一条词条，不会把整个词库塞进上下文。
- 查不到时不注入，让模型明确说不知道，而不是硬编。
- 普通查询不联网，不会把聊天内容发送给第三方。
- 塔菲和大肥鱼可以分别启用或关闭。
- 支持 `/tf_meme 词` 直接查询，不消耗模型 token。

## 使用

启动器 →“人格插件” →“梗百科（内置）”：

- “启用给此人格 / 关闭给此人格”：控制当前选中的人格。
- “下载 / 更新词库”：从官方公开 CDN 更新本地 SQLite。
- “上游项目”：打开 `dsh-memewiki` 说明。

QQ 命令：

```text
/tf_meme 哈基米
/tf_meme_status
/tf_meme_update
```

后两个命令仅管理员可用。更新词库会从网络下载约 17 MB 文件。

## 匹配顺序

1. 词条标题完全一致。
2. 别名完全一致。
3. 标题以查询词开头。
4. 查询句里包含完整标题，取最长标题。
5. 查询词至少三个字时，匹配标题中包含该词的条目。
6. 纯数字或英文短词可放宽到两个字。

感叹词、常见闲聊、状态问题和明显整句不会自动触发查询。

## 本地数据

```text
C:\tafei\astrbot\data\plugin_data\tafei_memewiki\memes.db
C:\tafei\astrbot\data\plugin_data\tafei_memewiki\config.json
```

`memes.db` 不进入 Git，也不打进公开安装包。启动器首次需要点击“下载 /
更新词库”。更新时先把文件下载到临时路径，验证 SQLite 文件头、
`PRAGMA integrity_check` 和条目数量后才原子替换；旧版本保留为
`memes.db.bak`。

## 上游与许可

- 上游代码：MIT License，Copyright (c) 2026 dsh-memewiki contributors。
- 原始灵感：AstrBot 插件 `astrbot_plugin_memewiki`，作者 in1t1a1。
- 词库来源：`cnmeme.wiki` 公开资料及原项目随包词库。
- 词库版权归原项目和 `cnmeme.wiki`，上游 `NOTICE` 明确不主张词库版权。

因此塔菲鱼公开仓库只包含适配代码和说明，不包含词库数据。用户在客户端
主动下载的词库只保存在本机运行时目录中。
