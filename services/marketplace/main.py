from fastapi import FastAPI


app = FastAPI(title="Auto-Selp Marketplace Listing")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "marketplace"}
