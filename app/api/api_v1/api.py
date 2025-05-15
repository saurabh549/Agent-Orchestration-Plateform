from fastapi import APIRouter

from app.api.api_v1.endpoints import users, auth, agents, crews, tasks, metrics

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(crews.router, prefix="/crews", tags=["crews"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(metrics.router, prefix="/metrics", tags=["metrics"]) 