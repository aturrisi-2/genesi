from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

app = FastAPI()

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Genesi</title>
    </head>
    <body>
        <h1>Genesi è online</h1>
        <p>Backend FastAPI funzionante.</p>
    </body>
    </html>
    """
