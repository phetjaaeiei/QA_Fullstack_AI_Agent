from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.api.auth import router as auth_router, get_current_user


app = FastAPI(title="QA Brain", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/test-cases")
async def list_test_cases(current_user=Depends(get_current_user)):
    return []
