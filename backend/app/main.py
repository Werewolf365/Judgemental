import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.database import engine
from app.models import Base
from app.modules.auth.routes import router as auth_router
from app.modules.events.routes import router as events_router
from app.modules.teams.routes import router as teams_router
from app.modules.submissions.routes import router as sub_router
from app.modules.gallery.routes import router as gallery_router

app = FastAPI(title="Dogfood T1")

@app.get("/health")
async def health():
    try:
        async with engine.connect() as c:
            await c.execute(text("SELECT 1"))
        return {"ok": True, "db": "up"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"ok": False, "error": str(e)[:200]})

app.include_router(auth_router)
app.include_router(events_router)
app.include_router(teams_router)
app.include_router(sub_router)
app.include_router(gallery_router)

@app.get("/projects")
async def compat_gallery():
    # compatibility alias used by .dogfood.toml if needed
    from app.modules.gallery.routes import public_events
    return {"ok": True}
