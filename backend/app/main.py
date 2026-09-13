from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.health import router as health_router
from .api.routes import (
    alerts_router,
    diagnostics_router,
    realtime_router,
    router as train_router,
)
from .api.settings import router as settings_router


app = FastAPI(
    title="Dynamic Train ETA API",
    version="1.0.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # Local development
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",

        # Vercel production
        "https://dynamic-train-eta-system-wj43.vercel.app",
        "https://dynamic-train-eta-system-wj43-9a7a7j67w-sih-80cc.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# API routers
app.include_router(health_router)
app.include_router(train_router)
app.include_router(alerts_router)
app.include_router(diagnostics_router)
app.include_router(realtime_router)
app.include_router(settings_router)