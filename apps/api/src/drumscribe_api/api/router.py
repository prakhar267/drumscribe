from fastapi import APIRouter

from .routes import admin, auth, events, exports, jobs, media, projects, system, uploads

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(auth.account_router)
api_router.include_router(projects.router)
api_router.include_router(uploads.router)
api_router.include_router(jobs.router)
api_router.include_router(events.router)
api_router.include_router(exports.router)
api_router.include_router(media.router)
api_router.include_router(media.waveform_router)
api_router.include_router(admin.router)
