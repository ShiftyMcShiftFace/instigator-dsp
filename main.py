import os
import traceback
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI(title="Instigator DSP")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return PlainTextResponse(
        f"ERROR on {request.url.path}:\n\n{tb}",
        status_code=500
    )

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Instigator DSP</title>
    <script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-gray-100 p-8">
      <h1 class="text-4xl font-bold text-indigo-700">Instigator DSP</h1>
      <p class="mt-4 text-lg">Minimal test page is live on Render.</p>
      <p class="mt-2">Health check: <a href="/health" class="text-blue-600 underline">/health</a></p>
    </body>
    </html>
    """

@app.get("/health")
def health():
    return {"status": "ok", "render": bool(os.getenv("RENDER")), "port": os.getenv("PORT")}

@app.get("/debug")
def debug():
    return {
        "env_keys": list(os.environ.keys()),
        "render": os.getenv("RENDER"),
        "port": os.getenv("PORT"),
        "cwd": os.getcwd()
    }
