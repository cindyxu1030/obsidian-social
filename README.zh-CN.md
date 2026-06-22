# obsidian-social

把小红书、抖音、微信公众号公开链接保存成 Obsidian source note 的 Codex skill。

[English README](README.md)

## 安全扫描

最新公开仓库扫描结果：

- 工具：SkillSpector `2.2.3`
- 扫描目标：`https://github.com/cindyxu1030/obsidian-social`
- 模式：静态扫描，`--no-llm`
- 结果：`SAFE`
- 风险等级：`LOW`
- 分数：`19/100`
- 日期：`2026-06-22`

剩余提示：SkillSpector 会提示转录脚本里有 `subprocess.run`，因为本地转录需要调用外部命令。脚本使用 `shell=False`，并且命令白名单只允许 `ffmpeg` 和 `whisper`。另外，SkillSpector 会把 MIT License 的标准法律措辞标成低风险 scope-creep false positive。

## 安装

让 Codex 安装：

```text
Install https://github.com/cindyxu1030/obsidian-social/tree/main/obsidian-social
```

或者直接运行 Codex 的 skill installer：

```bash
python3 "$HOME/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo cindyxu1030/obsidian-social \
  --path obsidian-social
```

安装后重启 Codex，让 skill 列表刷新。

## 一次安装包含什么

skill 安装会包含导入脚本、笔记模板、平台解析逻辑和本地转录 workflow。

它不会自动安装系统级转录依赖。文章导入和 metadata 抓取不需要额外依赖，但视频转录需要：

- `ffmpeg`
- OpenAI Whisper CLI，也就是终端里的 `whisper` 命令

检查当前电脑是否可转录：

```bash
python3 "$HOME/.codex/skills/obsidian-social/scripts/download_and_transcribe.py" --check-deps
```

常见 macOS 安装方式：

```bash
brew install ffmpeg
python3 -m pip install -U openai-whisper
```

这里的 `whisper` 指 OpenAI 的本地 Whisper CLI，不是 Wispr 听写软件。

## 默认设置

- Vault：`~/Documents/Obsidian Vault`
- 输出目录：`02-Sources`
- 媒体缓存：`~/.cache/obsidian-social`
- ASR：只用本地 Whisper，前提是已安装 `ffmpeg` 和 `whisper`

可选环境变量：

```bash
export OBSIDIAN_VAULT_PATH="/path/to/your/vault"
export OBSIDIAN_SOURCE_DIR="02-Sources"
export OBSIDIAN_SOCIAL_CACHE_DIR="$HOME/.cache/obsidian-social"
```

## 范围

这个 skill 用来把公开社媒内容整理成研究用 source note。它不发帖、不做互动自动化、不绕过登录墙、不导出浏览器凭证，默认也不接第三方 ASR API。
