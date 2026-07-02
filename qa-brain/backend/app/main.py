from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.test_cases import router as test_cases_router
from app.api.automation import router as automation_router
from app.api.security import router as security_router


app = FastAPI(title="QA Brain", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(test_cases_router)
app.include_router(automation_router)
app.include_router(security_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
