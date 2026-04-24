"""
Halo – yt-dlp Backend
======================
Cloudflare Workers から呼ばれる軽量バックエンドサーバー。
yt-dlp を使って YouTube 動画の直接 URL を返す。

要件:
  pip install fastapi uvicorn yt-dlp

起動:
  uvicorn ytdlp_server:app --host 0.0.0.0 --port 8000

本番環境では Fly.io / Railway / VPS などにデプロイし、
そのエンドポイントを YTDLP_BACKEND_URL に設定してください。
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
    """yt-dlp で動画URLを取得（同期）"""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "noplaylist": True,
        "skip_download": True,
        "cookiefile": "cookies.txt",
    }
    url = f"https://www.youtube.com/watch?v={video_id}"
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    # 結合フォーマットの場合は manifest_url、単体は url
    stream_url = info.get("url") or info.get("manifest_url")
    if not stream_url and info.get("requested_formats"):
        # 最初のビデオストリームを返す（ブラウザが対応できるもの）
        stream_url = info["requested_formats"][0].get("url")

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
    """動画の直接ストリームURLを返す"""
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
