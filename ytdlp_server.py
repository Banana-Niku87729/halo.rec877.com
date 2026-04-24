"""
Halo – yt-dlp Backend
"""

import asyncio
import json
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

app = FastAPI(title="Halo yt-dlp Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

def _extract(video_id: str) -> dict:
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        # ① mp4合体済みを最優先、なければ音声付き最良フォーマット、最後の手段はany
        "format": (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio"
            "/best[acodec!=none]/best"
        ),
        "noplaylist": True,
        "skip_download": True,
        "cookiefile": "cookies.txt",
        # ② merge_output_format は skip_download 時は不要だが念のため
        "merge_output_format": "mp4",
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
    url = f"https://www.youtube.com/watch?v={video_id}"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    # ── URL解決の優先順位 ──────────────────────────────
    # 1. トップレベルの url / manifest_url（merged or single stream）
    stream_url = info.get("url") or info.get("manifest_url")

    # 2. requested_formats がある = 映像+音声が分離されている
    #    → ブラウザは MSE が必要。HLS manifest があればそちらを使う
    if not stream_url and info.get("requested_formats"):
        # HLS/DASH manifest があれば優先（ブラウザで直接再生できる）
        stream_url = info.get("manifest_url")

        # なければ音声付きフォーマットを探す
        if not stream_url:
            for f in reversed(info.get("formats", [])):
                if f.get("url") and f.get("acodec") != "none":
                    stream_url = f["url"]
                    break

    # 3. フォールバック: formats の末尾（最高品質）
    if not stream_url:
        for f in reversed(info.get("formats", [])):
            if f.get("url"):
                stream_url = f["url"]
                break

    if not stream_url:
        raise ValueError("再生可能なURLが見つかりませんでした")

    return {
        "url": stream_url,
        "title": info.get("title", ""),
        "duration": info.get("duration"),
        "ext": info.get("ext", "mp4"),
    }

@app.get("/stream")
async def stream(id: str = Query(..., description="YouTube video ID")):
    if not id or len(id) > 20:
        raise HTTPException(status_code=400, detail="無効な動画IDです")
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _extract, id)
        return result
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=404, detail=f"動画を取得できませんでした: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/debug")
async def debug(id: str = Query(...)):
    """利用可能なフォーマット一覧を返す（デバッグ用）"""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "cookiefile": "cookies.txt",
    }
    url = f"https://www.youtube.com/watch?v={id}"
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    
    formats = [
        {
            "format_id": f.get("format_id"),
            "ext": f.get("ext"),
            "vcodec": f.get("vcodec"),
            "acodec": f.get("acodec"),
            "height": f.get("height"),
            "has_url": bool(f.get("url")),
        }
        for f in info.get("formats", [])
    ]
    return {"title": info.get("title"), "formats": formats}
