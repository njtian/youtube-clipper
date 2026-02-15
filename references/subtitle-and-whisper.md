# 字幕获取与无字幕转写（faster-whisper）

## 如何获得字幕

1. 下载时优先使用 YouTube 人工字幕，无则使用 YouTube 自动生成字幕（`download_video.py` 已配置 `writeautomaticsub=True`）。
2. **若仍无字幕**：使用 faster-whisper 从视频音频转写生成 VTT，由 `.env` 控制本地或远程、模型等。

## 无字幕时从音频转文字

- 调用 `scripts/transcribe_audio.py <视频路径>`，脚本会：
  - 用 FFmpeg 从视频提取 16kHz 单声道音频；
  - 按 `.env` 配置调用本地 faster-whisper 或远程转写 API；
  - 输出与下载字幕同名的 `<id>.en.vtt`，后续章节分析、剪辑流程一致。

## `.env` 配置（默认：本地 faster-whisper-small）

| 变量 | 说明 | 默认 |
|------|------|------|
| `WHISPER_ENABLED` | 是否在无字幕时启用转写 | `true` |
| `WHISPER_MODE` | `local` 或 `remote` | `local` |
| `WHISPER_MODEL` | 本地模型：tiny/base/small/medium/large-v2/large-v3 | `small` |
| `WHISPER_DEVICE` | 本地设备：cpu / cuda | `cpu` |
| `WHISPER_API_URL` | 远程模式时的 API 地址（POST 音频，返回 VTT 或 JSON segments） | 留空 |

- 本地模式需安装：`pip install faster-whisper`
- 远程模式：API 需接受 POST 音频并返回 VTT/SRT 文本或 `[{"start","end","text"}]` 的 JSON。**推荐使用的远程服务**见 [whisper-api.md](whisper-api.md)（faster-whisper ASR 服务，如 `http://localhost:10888/asr`），在 `.env` 中设置 `WHISPER_API_URL=http://localhost:10888/asr` 即可。
