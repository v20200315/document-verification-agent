from __future__ import annotations

from fastapi import FastAPI

from app.api.verification import router as verification_router

app = FastAPI(
    title="Document Verification API",
    description="CCC certificate and test report verification.",
    version="0.1.0",
)
app.include_router(verification_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
