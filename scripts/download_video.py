#!/usr/bin/env python3
"""
下载 YouTube 视频和字幕
使用 yt-dlp 下载视频（最高 1080p）和英文字幕
"""

import os
import shutil
import sys
import json
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    print("❌ Error: yt-dlp not installed")
    print("Please install: pip install yt-dlp")
    sys.exit(1)

from utils import (
    validate_url,
    sanitize_filename,
    format_file_size,
    get_video_duration_display,
    ensure_directory
)


def download_video(url: str, output_dir: str = None) -> dict:
    """
    下载 YouTube 视频和字幕

    Args:
        url: YouTube URL
        output_dir: 输出目录，默认为当前目录

    Returns:
        dict: {
            'video_path': 视频文件路径,
            'subtitle_path': 字幕文件路径,
            'title': 视频标题,
            'duration': 视频时长（秒）,
            'file_size': 文件大小（字节）
        }

    Raises:
        ValueError: 无效的 URL
        Exception: 下载失败
    """
    # 验证 URL
    if not validate_url(url):
        raise ValueError(f"Invalid YouTube URL: {url}")

    # 设置输出目录
    if output_dir is None:
        output_dir = Path.cwd()
    else:
        output_dir = Path(output_dir)

    output_dir = ensure_directory(output_dir)

    print(f"🎬 开始下载视频...")
    print(f"   URL: {url}")
    print(f"   输出目录: {output_dir}")

    # 可选：限制最大清晰度（默认 1080p）
    try:
        max_height = int(os.environ.get("YT_MAX_HEIGHT", "1080"))
    except ValueError:
        max_height = 1080

    # 可选：cookies 文件（解决 YouTube “confirm you’re not a bot”等验证）
    cookiefile = os.environ.get("YT_COOKIES") or os.environ.get("COOKIES_FILE")
    if not cookiefile:
        # 常见位置：当前目录 / 脚本目录 / 项目根（多级上溯）
        candidate_roots = [
            Path.cwd(),
            Path(__file__).resolve().parent,
            *list(Path(__file__).resolve().parents)[:6],
        ]
        for root in candidate_roots:
            for name in ("cookies.txt", "cookies.txt.bak"):
                p = root / name
                if p.exists():
                    cookiefile = str(p)
                    break
            if cookiefile:
                break

    # 可选：启用 JS runtime 与远程 EJS 组件（解决 YouTube n challenge）
    js_runtimes_env = os.environ.get("YT_JS_RUNTIMES")
    if js_runtimes_env:
        js_runtime_items = [s.strip() for s in js_runtimes_env.split(",") if s.strip()]
        js_runtimes = {}
        for item in js_runtime_items:
            name, _, path = item.partition(":")
            name = name.strip().lower()
            path = path.strip()
            if not name:
                continue
            js_runtimes[name] = {"path": path} if path else {}
    else:
        js_runtimes = {"node": {}} if shutil.which("node") else {}

    # 默认允许 ejs:github（不然常见会拿不到 formats）
    remote_components_env = os.environ.get("YT_REMOTE_COMPONENTS")
    if remote_components_env is None:
        remote_components = ["ejs:github"]
    else:
        remote_components = [s.strip() for s in remote_components_env.split(",") if s.strip()]

    # 可选：字幕语言（默认 en；可用 YT_SUB_LANGS 覆盖，如 "zh-Hans,en"）
    sub_langs_env = os.environ.get("YT_SUB_LANGS")
    if sub_langs_env:
        subtitleslangs = [s.strip() for s in sub_langs_env.split(",") if s.strip()]
    else:
        subtitleslangs = ["en"]

    # 可选：只下载字幕（跳过视频下载）
    skip_video = os.environ.get("YT_SKIP_VIDEO", "").strip() in ("1", "true", "TRUE", "yes", "YES")

    # 配置 yt-dlp 选项
    ydl_opts = {
        # 视频格式：最高 1080p，优先 mp4
        'format': (
            f'bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/'
            f'best[height<={max_height}][ext=mp4]/best'
        ),

        # 输出模板：包含视频 ID（避免特殊字符问题）
        'outtmpl': str(output_dir / '%(id)s.%(ext)s'),

        # 下载字幕
        'writesubtitles': True,
        'writeautomaticsub': True,  # 自动字幕作为备选
        'subtitleslangs': subtitleslangs,
        'subtitlesformat': 'vtt',   # VTT 格式

        # 不下载缩略图
        'writethumbnail': False,

        # 可选：跳过视频，仅下载字幕
        'skip_download': skip_video,

        # 静默模式（减少输出）
        'quiet': False,
        'no_warnings': False,

        # 进度钩子
        'progress_hooks': [_progress_hook],
    }

    # 追加可选参数（按需启用）
    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile
        print(f"   使用 cookies: {cookiefile}")
    if js_runtimes:
        ydl_opts["js_runtimes"] = js_runtimes
        print(f"   JS runtimes: {', '.join(js_runtimes.keys())}")
    if remote_components:
        ydl_opts["remote_components"] = remote_components
        print(f"   remote components: {', '.join(remote_components)}")
    if max_height != 1080:
        print(f"   最大分辨率: {max_height}p")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 提取信息
            print("\n📊 获取视频信息...")
            info = ydl.extract_info(url, download=False)

            title = info.get('title', 'Unknown')
            duration = info.get('duration', 0)
            video_id = info.get('id', 'unknown')

            print(f"   标题: {title}")
            print(f"   时长: {get_video_duration_display(duration)}")
            print(f"   视频ID: {video_id}")

            # 下载视频
            print(f"\n📥 开始下载...")
            info = ydl.extract_info(url, download=True)

            # 获取下载的文件路径
            video_filename = ydl.prepare_filename(info)
            video_path = Path(video_filename)

            # 查找字幕文件（优先匹配 <id>.<lang>.vtt，其次 <id>.vtt）
            subtitle_path = None
            stem = video_path.stem
            vtt_candidates = []
            vtt_candidates.extend(sorted(video_path.parent.glob(f"{stem}.*.vtt")))
            vtt_candidates.append(video_path.with_suffix(".vtt"))

            for candidate in vtt_candidates:
                if candidate.exists():
                    subtitle_path = candidate
                    break

            # 获取文件大小
            file_size = video_path.stat().st_size if video_path.exists() else 0

            # 验证下载结果
            if not video_path.exists():
                raise Exception("Video file not found after download")

            print(f"\n✅ 视频下载完成: {video_path.name}")
            print(f"   大小: {format_file_size(file_size)}")

            if subtitle_path and subtitle_path.exists():
                print(f"✅ 字幕下载完成: {subtitle_path.name}")
            else:
                print(f"⚠️  未找到英文字幕")
                print(f"   提示：某些视频可能没有字幕或需要自动生成")

            return {
                'video_path': str(video_path),
                'subtitle_path': str(subtitle_path) if subtitle_path else None,
                'title': title,
                'duration': duration,
                'file_size': file_size,
                'video_id': video_id
            }

    except Exception as e:
        print(f"\n❌ 下载失败: {str(e)}")
        raise


def _progress_hook(d):
    """下载进度回调"""
    if d['status'] == 'downloading':
        # 显示下载进度
        if 'downloaded_bytes' in d and 'total_bytes' in d and d['total_bytes']:
            percent = d['downloaded_bytes'] / d['total_bytes'] * 100
            downloaded = format_file_size(d['downloaded_bytes'])
            total = format_file_size(d['total_bytes'])
            speed = d.get('speed', 0)
            speed_str = format_file_size(speed) + '/s' if speed else 'N/A'

            # 使用 \r 实现进度条覆盖
            bar_length = 30
            filled = int(bar_length * percent / 100)
            bar = '█' * filled + '░' * (bar_length - filled)

            print(f"\r   [{bar}] {percent:.1f}% - {downloaded}/{total} - {speed_str}", end='', flush=True)
        elif 'downloaded_bytes' in d:
            # 无总大小信息时，只显示已下载
            downloaded = format_file_size(d['downloaded_bytes'])
            speed = d.get('speed', 0)
            speed_str = format_file_size(speed) + '/s' if speed else 'N/A'
            print(f"\r   下载中... {downloaded} - {speed_str}", end='', flush=True)

    elif d['status'] == 'finished':
        print()  # 换行


def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print("Usage: python download_video.py <youtube_url> [output_dir]")
        print("\nExample:")
        print("  python download_video.py https://youtube.com/watch?v=Ckt1cj0xjRM")
        print("  python download_video.py https://youtube.com/watch?v=Ckt1cj0xjRM ~/Downloads")
        sys.exit(1)

    url = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        result = download_video(url, output_dir)

        # 输出 JSON 结果（供其他脚本使用）
        print("\n" + "="*60)
        print("下载结果 (JSON):")
        print(json.dumps(result, indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"\n❌ 错误: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
