import os
import uuid
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Dict, Optional, List
from celery.result import AsyncResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from tasks import process_excel_task
from celery_app import celery_app
from database import get_db, engine, Base
from models import Prompt
from schemas import ProcessRequest, PromptUpdate, PromptResponse
from utils.prompt_manager import PromptManager

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Auto-Selp Product Processor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

from init_prompts import seed_prompts

@app.on_event("startup")
async def startup():
    await seed_prompts()

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.post("/upload")
async def upload_excel(file: UploadFile = File(...)):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only Excel files are allowed.")
    
    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())
    
    try:
        df = pd.read_excel(file_path, nrows=5)
        # Handle NaN values which are not JSON compliant
        df = df.fillna("")
        columns = df.columns.tolist()
        preview = df.to_dict(orient="records")
        return {
            "file_id": file_id,
            "filename": file.filename,
            "columns": columns,
            "preview": preview
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read excel: {e}")

@app.post("/process")
async def start_processing(request: ProcessRequest):
    files = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(request.file_id)]
    if not files:
        raise HTTPException(status_code=404, detail="File not found.")
    
    file_path = os.path.join(UPLOAD_DIR, files[0])
    task = process_excel_task.delay(file_path, request.column_mapping, request.llm_provider, request.kipris_enabled)
    return {"task_id": task.id}

@app.get("/status/{task_id}")
async def get_status(task_id: str):
    res = AsyncResult(task_id, app=celery_app)
    if res.state == 'PENDING':
        return {"state": res.state, "status": "Waiting for worker..."}
    elif res.state == 'PROGRESS':
        return {"state": res.state, "meta": res.info}
    elif res.state == 'SUCCESS':
        return {"state": res.state, "result": res.result}
    elif res.state == 'FAILURE':
        return {"state": res.state, "error": str(res.info)}
    return {"state": res.state}

@app.get("/download/{task_id}")
async def download_result(task_id: str):
    res = AsyncResult(task_id, app=celery_app)
    if res.state == 'SUCCESS':
        output_path = res.result.get("output_path")
        if output_path and os.path.exists(output_path):
            return FileResponse(output_path, filename=os.path.basename(output_path))
    raise HTTPException(status_code=404, detail="Result file not found or task not finished.")

# --- Admin Prompt Management ---

@app.get("/prompts", response_model=List[PromptResponse])
async def list_prompts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Prompt))
    return result.scalars().all()

@app.put("/prompts/{key}", response_model=PromptResponse)
async def update_prompt(key: str, prompt_in: PromptUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Prompt).where(Prompt.key == key))
    prompt = result.scalar_one_or_none()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    prompt.template = prompt_in.template
    if prompt_in.description:
        prompt.description = prompt_in.description
    
    await db.commit()
    await db.refresh(prompt)
    
    # Clear cache
    pm = PromptManager(db)
    await pm.clear_cache(key)
    
    return prompt
