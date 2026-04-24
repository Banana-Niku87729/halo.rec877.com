"""
Halo - yt-dlp Backend
"""

import os
import asyncio
from copy import deepcopy
from typing import Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

# 起動時にcookiesファイルを生成
COOKIES_PATH = Path("/tmp/cookies.txt")
_cookies_raw = os.environ.get("YOUTUBE_COOKIES", "")
if _cookies_raw:
    COOKIES_PATH.write_text(_cookies_raw)

app = FastAPI(title="Halo yt-dlp Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

BASE_YDL_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "skip_download": True,
    # cookiesが存在する場合のみ渡す
    **({"cookiefile": str(COOKIES_PATH)} if COOKIES_PATH.exists() else {}),
    "http_headers": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
    },
}

# Start with yt-dlp's default selection, then progressively relax it when a
# video does not expose the exact stream combination we first asked for.
STREAM_FORMAT_FALLBACKS: tuple[str | None, ...] = (
    None,
    "best/bestvideo+bestaudio",
    "best",
)


def _build_ydl_opts(format_selector: str | None = None) -> dict[str, Any]:
    opts = deepcopy(BASE_YDL_OPTS)
    if format_selector:
        opts["format"] = format_selector
    return opts


def _watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _fetch_video_info(video_id: str, format_selector: str | None = None) -> dict[str, Any]:
    with yt_dlp.YoutubeDL(_build_ydl_opts(format_selector)) as ydl:
        return ydl.extract_info(_watch_url(video_id), download=False)


def _extract_info_with_fallbacks(video_id: str) -> dict[str, Any]:
    last_error: Exception | None = None

    for format_selector in STREAM_FORMAT_FALLBACKS:
        try:
            return _fetch_video_info(video_id, format_selector)
        except yt_dlp.utils.DownloadError as error:
            last_error = error
            if "Requested format is not available" not in str(error):
                raise

    if last_error:
        raise last_error

    raise RuntimeError("yt-dlp did not return stream information")


def _entry_url(entry: dict[str, Any] | None) -> str | None:
    if not entry:
        return None
    return entry.get("url") or entry.get("manifest_url")


def _has_audio(entry: dict[str, Any]) -> bool:
    return entry.get("acodec") not in (None, "none")


def _has_video(entry: dict[str, Any]) -> bool:
    return entry.get("vcodec") not in (None, "none")


def _pick_stream_entry(info: dict[str, Any]) -> dict[str, Any] | None:
    if _entry_url(info):
        return info

    formats = info.get("formats") or []
    selectors = (
        lambda fmt: _entry_url(fmt) and _has_video(fmt) and _has_audio(fmt),
        lambda fmt: fmt.get("manifest_url"),
        lambda fmt: _entry_url(fmt) and _has_audio(fmt),
        lambda fmt: _entry_url(fmt),
    )

    for matches in selectors:
        for fmt in reversed(formats):
            if matches(fmt):
                return fmt

    return None


def _extract(video_id: str) -> dict[str, Any]:
    info = _extract_info_with_fallbacks(video_id)
    stream_entry = _pick_stream_entry(info)
    stream_url = _entry_url(stream_entry)

    if not stream_url:
        raise ValueError("再生可能なURLが見つかりませんでした")

    return {
        "url": stream_url,
        "title": info.get("title", ""),
        "duration": info.get("duration"),
        "ext": (stream_entry or {}).get("ext") or info.get("ext", "mp4"),
    }


@app.get("/api/stream")
async def stream(id: str = Query(..., description="YouTube video ID")):
    if not id or len(id) > 20:
        raise HTTPException(status_code=400, detail="無効な動画IDです")

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _extract, id)
        return result
    except yt_dlp.utils.DownloadError as error:
        raise HTTPException(
            status_code=404,
            detail=f"動画を取得できませんでした: {error}",
        ) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/formats")
async def formats(id: str):
    if not id or len(id) > 20:
        raise HTTPException(status_code=400, detail="無効な動画IDです")

    try:
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, _fetch_video_info, id, None)
    except yt_dlp.utils.DownloadError as error:
        raise HTTPException(
            status_code=404,
            detail=f"動画フォーマットを取得できませんでした: {error}",
        ) from error

    formats = [
        {
            "format_id": fmt.get("format_id"),
            "ext": fmt.get("ext"),
            "vcodec": fmt.get("vcodec"),
            "acodec": fmt.get("acodec"),
            "height": fmt.get("height"),
            "has_url": bool(_entry_url(fmt)),
        }
        for fmt in info.get("formats", [])
    ]
    return {"title": info.get("title"), "formats": formats}
