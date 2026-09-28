import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.database import engine
from app.models import Base
from app.modules.auth.routes import router as auth_router
from app.modules.admin.routes import router as admin_router
from app.modules.events.routes import router as events_router
from app.modules.teams.routes import router as teams_router
from app.modules.submissions.routes import router as sub_router
from app.modules.gallery.routes import router as gallery_router
from app.modules.judging.routes import router as judging_router
from app.modules.judging.judge import router as judge_router
from app.modules.judging.results import router as results_router
from app.modules.voting.routes import router as voting_router
from app.modules.judging import scheduler as auto_assign


@asynccontextmanager
async def lifespan(app: FastAPI):
    await auto_assign.start()
    yield
    await auto_assign.stop()


app = FastAPI(title="Dogfood T1", lifespan=lifespan)

@app.get("/health")
async def health():
    try:
        async with engine.connect() as c:
            await c.execute(text("SELECT 1"))
        return {"ok": True, "db": "up"}
    except Exception:
        import logging
        logging.getLogger("dogfood.health").exception("healthcheck failed")
        return JSONResponse(status_code=503, content={"ok": False, "error": "database unreachable"})

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(events_router)
app.include_router(teams_router)
app.include_router(sub_router)
app.include_router(gallery_router)
app.include_router(judging_router)
app.include_router(judge_router)
app.include_router(results_router)
app.include_router(voting_router)

@app.get("/projects")
async def compat_gallery():
    # compatibility alias used by .dogfood.toml if needed
    from app.modules.gallery.routes import public_events
    return {"ok": True}
