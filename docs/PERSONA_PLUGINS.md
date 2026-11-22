# 塔菲鱼人格插件格式

人格插件用于给某一位人格增加额外知识、表达习惯或触发规则。首版插件是
**声明式文本扩展**，不会执行 Python、系统命令或浏览器脚本。

## 使用方式

1. 打开塔菲鱼，点击“人格插件”。
2. 在顶部选择要安装给的人格，例如塔菲或大肥鱼。
3. 点击“安装插件包”，选择 `.tafeiplugin` 或 `.zip`。
4. 核对名称、作者、权限和触发词后确认安装。
5. 插件安装后会默认启用给所选人格。同一个人格插件也可以单独启用或关闭给
   其他已安装人格。

插件安装在本机：

```text
C:\tafei\local\persona_plugins
```

该目录不会提交到 Git。卸载插件只会删除插件包，不会删除聊天记录、记忆、
人格或声线。

## 插件包结构

`.tafeiplugin` 本质上是一个 ZIP 文件，根目录必须包含 `manifest.json`：

```text
my_plugin.tafeiplugin
├─ manifest.json
├─ prompt.md
├─ README.md
└─ LICENSE.txt
```

`manifest.json` 示例：

```json
{
  "schema": 1,
  "id": "example.weather_hint",
  "name": "天气提醒",
  "version": "1.0.0",
  "description": "用户问到天气时，提醒对方根据情况带伞。",
  "author": "你的名字",
  "permissions": ["prompt"],
  "prompt_file": "prompt.md",
  "triggers": ["天气", "下雨", "温度"],
  "homepage": "https://example.com/my-plugin"
}
```

字段说明：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `schema` | 是 | 当前固定为 `1` |
| `id` | 是 | 3-64 位小写字母、数字、点、下划线或短横线 |
| `name` | 是 | 客户端显示名称，最多 80 字 |
| `version` | 是 | 类似 `1.0.0` 的版本号 |
| `description` | 是 | 插件功能介绍，最多 500 字 |
| `author` | 否 | 作者名称，最多 80 字 |
| `permissions` | 是 | 首版仅支持 `["prompt"]` |
| `prompt_file` | 是 | 指向插件包里的 `.md` 或 `.txt` |
| `triggers` | 否 | 用户消息包含任一关键词时才注入；留空表示常驻 |
| `homepage` | 否 | 插件主页，只允许 HTTP/HTTPS |

## 权限与优先级

插件中的提示词被放在单独的“人格插件扩展”区块中。它只能增加知识、口癖或
场景建议，不能覆盖：

- 人格的基础身份和边界
- 平台安全规则和隐私规则
- 管理员指令
- API Key、账号会话等敏感信息保护规则

插件文本如果要求读取密钥、执行命令或绕过安全限制，模型应忽略该要求。

## 安全限制

塔菲鱼会在安装前验证：

- 压缩包小于 1 MB，最多 32 个文件。
- 只允许 `.json`、`.md`、`.txt` 文件。
- 不允许 `.py`、`.exe`、`.dll`、`.bat`、`.ps1`、`.js`、快捷方式等文件。
- 不允许绝对路径、`..` 路径穿越、符号链接或加密 ZIP。
- 清单、版本、权限、提示词文件和触发词必须合法。

客户端不会把插件 Python 代码加载进 AstrBot 进程。以后如果增加代码插件或
命令插件，应使用独立进程、权限清单、签名校验和用户明确授权，不能直接复用
当前的文本插件权限。

## 开发示例

仓库内置示例：

```text
C:\tafei\examples\persona_plugins\weather_hint
```

在该目录中打包：

```powershell
Compress-Archive -Path .\* -DestinationPath .\weather_hint.tafeiplugin -Force
```

升级同一个 `id` 的插件时，可以直接在插件中心选择新包执行更新。已经启用该
插件的人格会保留启用状态。
