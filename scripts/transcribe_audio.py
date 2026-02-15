#!/usr/bin/env python3
"""
无字幕时从视频/音频生成 VTT 字幕（faster-whisper 本地或远程 API）。
根据 .env 中 WHISPER_* 配置执行，默认本地 faster-whisper-small。
"""

import os
import sys
import json
import tempfile
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent


def _load_env():
    """从 skill 根目录加载 .env"""
    try:
        from dotenv import load_dotenv
        load_dotenv(SKILL_ROOT / ".env")
    except ImportError:
        pass


def _get_whisper_config():
    _load_env()
    enabled = os.environ.get("WHISPER_ENABLED", "true").strip().lower() in ("1", "true", "yes")
    mode = (os.environ.get("WHISPER_MODE") or "local").strip().lower()
    model = (os.environ.get("WHISPER_MODEL") or "small").strip().lower()
    device = (os.environ.get("WHISPER_DEVICE") or "cpu").strip().lower()
    api_url = (os.environ.get("WHISPER_API_URL") or "").strip()
    return {"enabled": enabled, "mode": mode, "model": model, "device": device, "api_url": api_url}


def _extract_audio(video_path: Path, out_audio_path: Path) -> None:
    """用 FFmpeg 从视频提取 16kHz 单声道 WAV，供 Whisper 使用。"""
    ffmpeg = (os.environ.get("FFMPEG_PATH") or "ffmpeg").strip() or "ffmpeg"
    cmd = [
        ffmpeg, "-y", "-i", str(video_path),
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(out_audio_path)
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _segments_to_vtt(segments) -> str:
    """将 segments（每项含 start, end, text）转为 VTT 文本。"""
    from utils import seconds_to_time
    lines = ["WEBVTT", ""]
    for s in segments:
        start = s.get("start", 0)
        end = s.get("end", 0)
        text = (s.get("text") or "").strip()
        if not text:
            continue
        start_str = seconds_to_time(start, include_hours=True, use_comma=False)
        end_str = seconds_to_time(end, include_hours=True, use_comma=False)
        lines.append(f"{start_str} --> {end_str}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _transcribe_local(audio_path: Path, model: str, device: str):
    """本地 faster-whisper 转写，返回 segment 列表。"""
    from faster_whisper import WhisperModel
    print(f"   加载模型: {model} (device={device})...")
    model_instance = WhisperModel(model, device=device, compute_type="int8" if device == "cpu" else "float16")
    print(f"   转写中...")
    segments_iter, _ = model_instance.transcribe(str(audio_path), language=None, vad_filter=True)
    segments = [{"start": s.start, "end": s.end, "text": s.text} for s in segments_iter]
    return segments


def _parse_srt_to_segments(body: str):
    """将 SRT 文本解析为 [{"start","end","text"}]。SRT 时间戳为逗号分隔毫秒，需先替换为点。"""
    import re
    from utils import time_to_seconds
    segments = []
    blocks = body.strip().split("\n\n")
    for block in blocks:
        lines = [ln.strip() for ln in block.strip().split("\n") if ln.strip()]
        if len(lines) < 2:
            continue
        # 第一行可能为序号，第二行为时间轴
        time_line = None
        text_lines = []
        for line in lines:
            if "-->" in line:
                time_line = line
            else:
                text_lines.append(line)
        if not time_line or not text_lines:
            continue
        parts = time_line.split("-->")
        if len(parts) != 2:
            continue
        start_str = parts[0].strip().replace(",", ".")
        end_str = parts[1].strip().replace(",", ".")
        try:
            start = time_to_seconds(start_str)
            end = time_to_seconds(end_str)
        except ValueError:
            continue
        text = " ".join(text_lines).strip()
        if text:
            segments.append({"start": start, "end": end, "text": text})
    return segments


def _transcribe_remote(audio_path: Path, api_url: str):
    """远程 API 转写：POST 音频（multipart audio_file），响应为 VTT/SRT 文本或 JSON segments。"""
    import urllib.request
    import uuid

    # 使用 multipart/form-data，兼容 faster-whisper ASR 等 API（见 references/whisper-api.md）
    boundary_str = uuid.uuid4().hex
    boundary = boundary_str.encode()
    with open(audio_path, "rb") as f:
        audio_data = f.read()
    output_format = os.environ.get("WHISPER_API_OUTPUT_FORMAT", "srt").strip().lower()
    language = os.environ.get("WHISPER_API_LANGUAGE", "auto").strip()

    header1 = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="audio_file"; filename="audio.wav"\r\n'
        b"Content-Type: application/octet-stream\r\n\r\n"
    )
    part2 = (
        b"\r\n--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="output_format"\r\n\r\n'
        + output_format.encode() + b"\r\n"
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="language"\r\n\r\n'
        + language.encode() + b"\r\n"
        b"--" + boundary + b"--\r\n"
    )
    data = header1 + audio_data + part2

    req = urllib.request.Request(api_url, data=data, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary_str}")

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        raise RuntimeError(f"远程转写请求失败: {e}") from e

    # 若返回 JSON：array [{"start","end","text"}] 或 object {"segments": [...]}
    try:
        raw = json.loads(body)
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict) and "segments" in raw:
            return raw["segments"]
    except json.JSONDecodeError:
        pass

    # 若返回为 VTT 文本
    if body.strip().upper().startswith("WEBVTT"):
        import re
        from utils import time_to_seconds
        content = re.sub(r"^WEBVTT.*?\n\n", "", body, flags=re.DOTALL)
        segments = []
        for block in content.strip().split("\n\n"):
            lines = block.strip().split("\n")
            if len(lines) < 2:
                continue
            if "-->" in lines[0]:
                ts = lines[0]
                text = " ".join(lines[1:])
            else:
                continue
            parts = ts.split("-->")
            if len(parts) != 2:
                continue
            start = time_to_seconds(parts[0].strip().replace(",", "."))
            end = time_to_seconds(parts[1].strip().replace(",", "."))
            if text.strip():
                segments.append({"start": start, "end": end, "text": text.strip()})
        return segments

    # 若返回为 SRT 文本（如 faster-whisper ASR 服务 output_format=srt）
    if _looks_like_srt(body):
        return _parse_srt_to_segments(body)

    raise ValueError("远程 API 返回既不是 JSON segments 也不是 VTT/SRT 文本")


def _looks_like_srt(text: str) -> bool:
    """简单判断是否为 SRT 内容（序号 + 时间轴 -->）。"""
    trimmed = text.strip()
    if not trimmed or trimmed.startswith("{"):
        return False
    return "-->" in trimmed[:200]


def transcribe_audio(video_path: str, output_vtt_path: str = None) -> str:
    """
    从视频文件生成 VTT 字幕（根据 .env 使用本地 faster-whisper 或远程 API）。

    Args:
        video_path: 视频文件路径
        output_vtt_path: 输出 VTT 路径，默认为 .env 中 OUTPUT_DIR 下的 <视频stem>.en.vtt

    Returns:
        生成的 VTT 文件路径

    Raises:
        FileNotFoundError: 视频不存在
        RuntimeError: 未启用 Whisper 或配置错误
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    cfg = _get_whisper_config()
    if not cfg["enabled"]:
        raise RuntimeError("未启用 Whisper（.env 中 WHISPER_ENABLED=false），无法从音频生成字幕")

    if output_vtt_path is None:
        from utils import get_output_base_dir
        output_vtt_path = get_output_base_dir() / f"{video_path.stem}.en.vtt"
    else:
        output_vtt_path = Path(output_vtt_path)

    print(f"🎤 从音频生成字幕（faster-whisper，模式: {cfg['mode']}）...")
    print(f"   视频: {video_path.name}")

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    audio_path = Path(tmp.name)

    try:
        _extract_audio(video_path, audio_path)
        print(f"   已提取音频: 16kHz 单声道")

        if cfg["mode"] == "remote":
            if not cfg["api_url"]:
                raise RuntimeError("WHISPER_MODE=remote 时需在 .env 中配置 WHISPER_API_URL")
            segments = _transcribe_remote(audio_path, cfg["api_url"])
        else:
            segments = _transcribe_local(audio_path, cfg["model"], cfg["device"])

        if not segments:
            raise RuntimeError("转写结果为空")

        vtt_content = _segments_to_vtt(segments)
        output_vtt_path.parent.mkdir(parents=True, exist_ok=True)
        output_vtt_path.write_text(vtt_content, encoding="utf-8")
        print(f"✅ 字幕已生成: {output_vtt_path.name}（{len(segments)} 条）")
        return str(output_vtt_path)
    finally:
        if audio_path.exists():
            audio_path.unlink(missing_ok=True)


def main():
    if len(sys.argv) < 2:
        print("Usage: python transcribe_audio.py <video_path> [output.vtt]")
        print("  从视频提取音频并用 faster-whisper（本地或远程）生成 VTT 字幕。")
        print("  配置见 .env：WHISPER_MODE、WHISPER_MODEL、WHISPER_API_URL 等。")
        sys.exit(1)

    video_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        out = transcribe_audio(video_path, output_path)
        print(out)
    except Exception as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
