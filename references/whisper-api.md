# faster-whisper ASR 服务 API

适用于本 Skill 的远程转写（`.env` 中 `WHISPER_MODE=remote`、`WHISPER_API_URL` 指向本服务）。

---

## 服务地址

```
http://localhost:10888
```

---

## 主要端点

### 1. 健康检查

```
GET /health
```

### 2. 语音转文字

```
POST /asr
```

**参数:**

- `audio_file` - 音频文件（必填）
- `language` - 语言（默认 `auto`）
- `output_format` - 输出格式：`json` / `srt` / `txt`（默认 `json`）

本 Skill 调用时会使用 `output_format=srt`，以便获得带时间戳的字幕并转换为 VTT。

---

## 调用示例

```bash
curl -X POST http://localhost:10888/asr \
  -F "audio_file=@test.m4a" \
  -F "language=zh"
```

带格式与语言：

```bash
curl -X POST http://localhost:10888/asr \
  -F "audio_file=@audio.wav" \
  -F "language=auto" \
  -F "output_format=srt"
```

---

## 返回结果

**output_format=json 时示例：**

```json
{
  "text": "识别内容",
  "language": "zh",
  "duration": 10.5
}
```

**output_format=srt 时** 返回 SRT 字幕文本，供本 Skill 解析并转为 VTT。

---

## 在本 Skill 中的配置

在 youtube-clipper 目录的 `.env` 中设置：

```env
WHISPER_MODE=remote
WHISPER_API_URL=http://localhost:10888/asr
```

无字幕时 `transcribe_audio.py` 会向该地址 POST 音频（multipart `audio_file`），并请求 `output_format=srt`，再将返回的 SRT 转为 VTT 供后续章节分析使用。
