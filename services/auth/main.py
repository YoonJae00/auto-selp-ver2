from fastapi import FastAPI

app = FastAPI(title="Auto-Selp Auth Service")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
