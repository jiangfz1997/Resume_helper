import asyncio
import logging
import sys
import traceback

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import auth, profile, resume, sessions, users
from app.api.routes import templates
from app.api.routes import chat
from app.api.routes.chat import stream_router as chat_stream_router
from app.core.config import settings
from app.core.logging import setup_logging
from dotenv import load_dotenv

load_dotenv()
setup_logging(debug=settings.debug)

logger = logging.getLogger(__name__)

app = FastAPI(title="Resume Tailoring Assistant", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    tb = traceback.format_exc()
    logger.error("Unhandled exception | %s %s\n%s", request.method, request.url.path, tb)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "traceback": tb},
    )


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(profile.router)
app.include_router(resume.router)
app.include_router(sessions.router)
app.include_router(templates.router)
app.include_router(chat_stream_router)   # must be before chat.router (avoids /{session_id} 405)
app.include_router(chat.router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="debug")
