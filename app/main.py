"""Application entry point: python -m uvicorn app.main:app --reload."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app import models
from app.config import APP_DIR, UPLOAD_DIR
from app.database import engine
from app.routes.web import app as web_router
from app.routes.web import templates
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


@asynccontextmanager
async def lifespan(app):
    models.Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="DJ WASH · Gestão de estética automotiva", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.include_router(web_router)


def error_response(request, status, message):
    if "text/html" in request.headers.get("accept", ""):
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={"status": status, "message": message},
            status_code=status,
        )
    return JSONResponse({"detail": message}, status_code=status)


@app.exception_handler(HTTPException)
async def http_error(request, error):
    return error_response(request, error.status_code, error.detail)


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    return error_response(
        request,
        422,
        "Confira os campos obrigatórios. Valores devem ser não negativos e volumes devem ser maiores que zero.",
    )
