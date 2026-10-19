print("STARTING INSTIGATOR DSP")
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok", "msg": "alive"}

@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Instigator DSP</title></head>
    <body style="font-family:sans-serif;padding:2rem">
      <h1>Instigator DSP</h1>
      <p>Minimal service is running.</p>
      <p><a href="/health">Health check</a></p>
    </body>
    </html>
    """

print("APP READY")
