## 说明

这份文档描述我在本工作区里**实际安装并修改过**的 `youtube-clipper` skill（YouTube 视频智能剪辑工具），包括：位置、组成、工作方式/原理/功能、使用方法，以及在其它机器上的部署建议。

> 上游技能页：[`skills.sh/op7418/youtube-clipper-skill/youtube-clipper`](https://skills.sh/op7418/youtube-clipper-skill/youtube-clipper)

---

## 1) 在哪里

- **技能根目录**：`/root/clawd/skills/youtube-clipper/`
- **核心脚本目录**：`/root/clawd/skills/youtube-clipper/scripts/`
- **本次实测输出示例**：
  - 下载输出：`/root/clawd/youtube-clipper-output/`
  - 剪辑输出：`/root/clawd/youtube-clips/`

---

## 2) 它的组成

- **入口说明**
  - `SKILL.md`：技能说明与推荐工作流（6 个阶段）
- **核心脚本（`scripts/`）**
  - `download_video.py`：下载视频与字幕（我对它做了主要改造，见下文）
  - `analyze_subtitles.py`：解析 VTT → 输出带时间戳的全文字幕 + 分析摘要（供“章节划分”使用）
  - `clip_video.py`：用 FFmpeg 按时间剪辑视频（默认 `-c copy` 无重编码）
  - `extract_subtitle_clip.py`：从 VTT 里按时间段抽取字幕并转为 SRT
  - `translate_subtitles.py` / `merge_bilingual_subtitles.py`：字幕翻译与合并双语（需要对应的翻译/模型环境）
  - `burn_subtitles.py`：硬字幕烧录（依赖 FFmpeg libass）
  - `generate_summary.py`：生成“总结文案模板”（脚本本身会写模板；真正“自动写文案”通常依赖 Agent/Skill 运行环境）
  - `utils.py`：时间格式转换、路径与通用工具函数
- **参考资料（`references/`）**
  - `yt-dlp-guide.md`、`ffmpeg-guide.md`、`subtitle-formatting.md` 等
- **其它**
  - `README.zh-CN.md`、`TECHNICAL_NOTES.md` 等说明文件

---

## 3) 工作方式、原理、功能

### 工作方式（阶段化流水线）

按 `SKILL.md` 的 6 阶段：

- **阶段 1：环境检测**
  - `yt-dlp` 是否可用
  - `ffmpeg` 是否可用且支持 `libass`（硬字幕必需）
  - Python 依赖（例如 `pysrt`）
- **阶段 2：下载视频与字幕**
  - 使用 `yt-dlp`/`yt_dlp` 拉取视频流与字幕（字幕优先人工字幕，不存在则自动字幕）
- **阶段 3：字幕分析与章节划分**
  - `analyze_subtitles.py` 将 VTT 转成带时间戳的“连续文本”
  - 章节划分原则：2–5 分钟粒度、按主题切分、覆盖完整内容（本工作区里我按 3 分钟网格做了可用的章节分段，并给了标题/摘要/关键词）
- **阶段 4：选择章节**
  - 交互选择要剪哪些章节（可多选）
- **阶段 5：剪辑与字幕处理**
  - `clip_video.py` 剪视频
  - `extract_subtitle_clip.py` 抽字幕段并转 SRT
  - （可选）翻译字幕/合并双语/烧录硬字幕/生成总结文案
- **阶段 6：组织输出目录**
  - 每章一个文件夹，包含 clip、字幕、summary 等

### 核心原理（为什么能跑通 YouTube）

YouTube 近年来对 `yt-dlp` 增加了 JS challenge（常见日志：`n challenge`）。在本工作区里，单靠 cookies 仍可能拿不到 formats。

我在 `download_video.py` 中补齐了两点以解决此问题：

- **JS runtime**：优先使用 `node`（当系统存在 `node` 时自动启用）
- **远程 EJS 组件**：默认允许 `ejs:github`（等价于命令行 `--remote-components ejs:github`），让 `yt-dlp` 能下载并使用挑战求解脚本

### 功能概述

- 下载：YouTube 视频（可限最高分辨率）+ 字幕（可指定语言）
- 分析：VTT → 结构化字幕文本（含时长、条数、预估章节数）
- 剪辑：按时间段切片输出多个短视频
- 字幕：抽取切片字幕并导出 SRT（可扩展到翻译/双语/硬字幕）
- 文案：为每个章节生成总结文案文件（模板/或在 Agent 环境生成完整文案）

---

## 4) 如何使用（本机 / 本工作区）

### 4.1 下载视频（带 cookies + JS challenge 支持）

建议通过环境变量启用（避免把 cookies 路径写死到脚本里）：

```bash
cd /root/clawd/skills/youtube-clipper

COOKIES_FILE=/root/clawd/cookies.txt.bak \
YT_JS_RUNTIMES=node \
YT_REMOTE_COMPONENTS=ejs:github \
YT_MAX_HEIGHT=1080 \
python3 scripts/download_video.py "https://www.youtube.com/watch?v=<VIDEO_ID>" /root/clawd/youtube-clipper-output
```

### 4.2 下载字幕（指定语言）

这个视频实测 **没有英文字幕**，但有 `zh-Hans` 自动字幕。可这样拉字幕：

```bash
COOKIES_FILE=/root/clawd/cookies.txt.bak \
YT_JS_RUNTIMES=node \
YT_REMOTE_COMPONENTS=ejs:github \
YT_SUB_LANGS=zh-Hans \
python3 scripts/download_video.py "https://www.youtube.com/watch?v=<VIDEO_ID>" /root/clawd/youtube-clipper-output
```

> 说明：`download_video.py` 内部使用 `yt_dlp` 下载；当 YouTube 需要 JS challenge 时，`YT_JS_RUNTIMES` + `YT_REMOTE_COMPONENTS` 很关键。

### 4.3 解析字幕并准备“章节分析数据”

```bash
python3 scripts/analyze_subtitles.py /root/clawd/youtube-clipper-output/<VIDEO_ID>.<lang>.vtt 180 /root/clawd/youtube-clipper-output/<VIDEO_ID>.analysis.json
```

其中 `180` 表示目标章节时长 180 秒（3 分钟）。

### 4.4 剪辑视频 + 抽取字幕（SRT）

```bash
# 剪视频
python3 scripts/clip_video.py /root/clawd/youtube-clipper-output/<VIDEO_ID>.mp4 00:00:00 00:03:00 /root/clawd/youtube-clips/<RUN_ID>/01_clip.mp4

# 抽字幕并转 SRT
python3 scripts/extract_subtitle_clip.py /root/clawd/youtube-clipper-output/<VIDEO_ID>.<lang>.vtt 00:00:00 00:03:00 /root/clawd/youtube-clips/<RUN_ID>/01.srt
```

### 4.5 我为 `download_video.py` 新增/支持的环境变量

- **`COOKIES_FILE` / `YT_COOKIES`**：Netscape 格式 cookies 文件路径（用于登录态/反机器人校验）
- **`YT_JS_RUNTIMES`**：JS runtime（逗号分隔），支持 `node`，也支持 `node:/path/to/node` 形式指定路径
- **`YT_REMOTE_COMPONENTS`**：远程组件白名单（逗号分隔）。默认启用 `ejs:github`
- **`YT_MAX_HEIGHT`**：最大分辨率（默认 `1080`），例如 `360`
- **`YT_SUB_LANGS`**：字幕语言（逗号分隔），例如 `zh-Hans,en`
- **`YT_SKIP_VIDEO`**：仅下载字幕（`1/true/yes` 视为开启；注意：上游 `yt_dlp` 在某些场景仍会探测 formats）

---

## 5) 其它机器如何部署

### 5.1 安装 skill

在目标机器上执行（需要 Node.js 与 `npx`）：

```bash
npx skills add https://github.com/op7418/youtube-clipper-skill --skill youtube-clipper -y
```

### 5.2 依赖要求（建议最低清单）

- **Python 3**
  - `pip install yt-dlp pysrt python-dotenv`
- **FFmpeg**
  - 需要 `ffmpeg` 可执行文件
  - 若要硬字幕烧录：必须有 `libass`（`ffmpeg -filters | grep subtitles` 能看到 `subtitles`/`ass`）
- **JS runtime（推荐）**
  - 安装 `node`（YouTube JS challenge 常需要）
- **网络访问**
  - `ejs:github` 会从 GitHub 拉取挑战求解脚本（等价于 `--remote-components ejs:github`）；目标机器需能访问 GitHub

### 5.3 cookies 获取与使用

- 从 Chrome 导出 Netscape 格式 cookies（你当前的 `cookies.txt.bak` 就是此类文件）
- 使用时在命令行设置：
  - `COOKIES_FILE=/path/to/cookies.txt`

> 注意：cookies 属于敏感信息，建议只放在目标机器本地，避免提交到仓库。

### 5.4 典型的“跨机器可复现”命令

```bash
COOKIES_FILE=/path/to/cookies.txt \
YT_JS_RUNTIMES=node \
YT_REMOTE_COMPONENTS=ejs:github \
python3 scripts/download_video.py "https://www.youtube.com/watch?v=<VIDEO_ID>" ./youtube-clipper-output
```

