import asyncio
import yt_dlp
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

YDL_OPTS_BASE = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
}

def _extract(video_id: str) -> dict:
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        opts = {
            **YDL_OPTS_BASE,
            "format": "best[ext=mp4]/best",  # mp4優先、なければ最善
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "url": info["url"],
                "title": info.get("title", ""),
                "duration": info.get("duration", 0),
                "ext": info.get("ext", "mp4"),
            }
    except Exception as e:
        raise ValueError(f"yt-dlp Error: {str(e)}")

def _get_formats(video_id: str) -> dict:
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        with yt_dlp.YoutubeDL(YDL_OPTS_BASE) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info.get("title", ""),
                "formats": [
                    {
                        "format_id": f.get("format_id", ""),
                        "ext": f.get("ext", ""),
                        "url": f.get("url", ""),
                    }
                    for f in info.get("formats", [])
                ],
            }
    except Exception as e:
        raise ValueError(f"yt-dlp Error: {str(e)}")

@app.get("/api/stream")
async def stream(id: str = Query(..., description="YouTube video ID")):
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _extract, id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/api/formats")
async def formats(id: str = Query(...)):
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _get_formats, id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/health")
async def health():
    return {"status": "ok"}
