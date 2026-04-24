"""
Halo - pytubefix Backend
"""

import asyncio
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pytubefix import YouTube

app = FastAPI(title="Halo pytubefix Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

def _watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"

def _extract(video_id: str) -> dict:
    try:
        # client='WEB' の他に 'ANDROID' や 'TV' などが指定可能です。
        # ブロックされやすい場合はクライアントを変更すると通ることがあります。
        yt = YouTube(_watch_url(video_id), client='WEB')
        
        # 映像と音声が含まれているプログレッシブストリームの中で最高画質を取得 (通常720p)
        stream = yt.streams.get_highest_resolution()
        
        if not stream:
            # 見つからない場合は何らかのストリームをフォールバックとして取得
            stream = yt.streams.first()

        if not stream:
            raise ValueError("再生可能なストリームが見つかりませんでした")

        return {
            "url": stream.url,
            "title": yt.title,
            "duration": yt.length,
            "ext": stream.subtype,
        }
    except Exception as e:
        raise ValueError(f"動画の取得に失敗しました: {e}")

@app.get("/stream")
async def stream(id: str = Query(..., description="YouTube video ID")):
    if not id or len(id) > 20:
        raise HTTPException(status_code=400, detail="無効な動画IDです")

    try:
        loop = asyncio.get_running_loop()
        # pytubefixの通信処理は同期的なので、イベントループをブロックしないよう別スレッドで実行
        result = await loop.run_in_executor(None, _extract, id)
        return result
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/formats")
async def formats(id: str):
    if not id or len(id) > 20:
        raise HTTPException(status_code=400, detail="無効な動画IDです")

    try:
        def _get_formats():
            yt = YouTube(_watch_url(id), client='WEB')
            formats_list = [
                {
                    "format_id": str(stream.itag),
                    "ext": stream.subtype,
                    "vcodec": stream.video_codec,
                    "acodec": stream.audio_codec,
                    "height": getattr(stream, 'resolution', None),
                    "has_url": bool(stream.url),
                }
                for stream in yt.streams
            ]
            return {"title": yt.title, "formats": formats_list}
            
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _get_formats)
        return result
    except Exception as error:
        raise HTTPException(status_code=404, detail=str(error))
