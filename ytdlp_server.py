import asyncio
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pytubefix import YouTube

app = FastAPI()

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
        # clientを 'ANDROID' に変更（Renderのようなクラウド環境で通りやすい）
        yt = YouTube(_watch_url(video_id), client='ANDROID')
        
        # プログレッシブストリームを取得
        stream = yt.streams.get_highest_resolution()
        
        if not stream:
            raise ValueError("再生可能なストリームが見つかりませんでした")

        return {
            "url": stream.url,
            "title": yt.title,
            "duration": yt.length,
            "ext": stream.subtype,
        }
    except Exception as e:
        # 詳細なエラーをログに出すために例外をそのまま投げる
        raise ValueError(f"Pytube Error: {str(e)}")

# Workerの指定に合わせて /api/stream に変更
@app.get("/api/stream")
async def stream(id: str = Query(..., description="YouTube video ID")):
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _extract, id)
        return result
    except ValueError as error:
        # 404だと紛らわしいので、中身がエラーの時は詳細を添えて400や500で返す
        raise HTTPException(status_code=500, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail="Internal Server Error")

# Workerの指定に合わせて /api/formats に変更
@app.get("/api/formats")
async def formats(id: str):
    try:
        def _get_formats():
            yt = YouTube(_watch_url(id), client='ANDROID')
            return {
                "title": yt.title,
                "formats": [
                    {"format_id": str(s.itag), "ext": s.subtype, "url": s.url} 
                    for s in yt.streams
                ]
            }
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _get_formats)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))

@app.get("/health")
async def health():
    return {"status": "ok"}
