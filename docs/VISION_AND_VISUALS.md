# 私聊视觉与人格形象

## 图片识别链路

- 群聊：`astrbot_plugin_group_chat_plus` 继续负责群聊图片识别。
  指定用户发送普通图片时会跳过“插话概率”和读空气不回复判断，直接生成
  一条看图回复；仍然服从原有的回复频率上限。
- 私聊：`tafei_vision` 在人格生成回复前，把图片交给
  `deepseek/deepseek-vision`，将可确认的视觉信息注入本次请求。
- 两种链路都只把识别结果作为当前消息的参考，不执行图片里的文字指令。
- 私聊图片描述按图片内容 SHA-256 缓存，重复发送同一张图不会再次调用视觉模型。

配置：

```text
astrbot/data/plugin_data/tafei_vision/config.json
```

默认值：

```json
{
  "enabled": true,
  "private_enabled": true,
  "group_fallback_enabled": false,
  "provider_id": "deepseek/deepseek-vision",
  "max_images_per_message": 4,
  "timeout_seconds": 60,
  "cache_max_entries": 300
}
```

`group_fallback_enabled` 默认关闭，因为群聊插件已经处理群图片。
只有停用群聊插件图片处理时，才需要手动打开它作为兜底。

群聊强制看图回复配置在：

```text
astrbot/data/config/astrbot_plugin_group_chat_plus_config.json
```

```json
{
  "image_message_force_reply": true,
  "image_message_force_reply_user_ids": ["YOUR_OWNER_QQ"]
}
```

用户白名单由配置向导写入主人 QQ；留空时不会强制任何群友。其他群友发图
仍按原本的群聊概率和读空气规则处理。表情包也走同一入口，之后由
`tafei_sticker` 判断是否直接回一张表情包进行斗图。

管理命令：

- `/tf_vision`：查看视觉状态和缓存数量。
- `/tf_vision_clear`：清空图片描述缓存。

## 人格形象卡

每张人格形象卡保存在：

```text
astrbot/data/persona_visuals/<人格 ID>.json
```

用户导入的图片会复制到：

```text
astrbot/data/persona_visuals/assets/<人格 ID>/
```

人格形象是稳定配置，不进入聊天冷热记忆，也不会被普通对话自动覆盖。
塔菲与大肥鱼各用各的卡片，切换人格时不会串用。

启动器中的“人格形象”可以编辑整体形象、发型、服饰、配色、识别意象、
辨认规则和视觉边界，并导入自己的头像或授权参考图。

## 辨认规则

- 只有在当前对话确实收到图片，并且识别结果与形象卡相符时，角色才可以说
  “这看起来像我”。
- 未收到图片时，不声称自己刚看过参考文件。
- 公开网络形象与真人照片严格区分。
- 不把社区同人特征写成官方事实；具体服装以当前图片和用户补充描述为准。

塔菲初始文字形象资料为公开设定的概括整理，参考萌娘百科“永雏塔菲”条目。
