import os
import uuid
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Dict
from celery.result import AsyncResult

from tasks import process_excel_task
from celery_app import celery_app

app = FastAPI(title="Auto-Selp Product Processor")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

class ProcessRequest(BaseModel):
    file_id: str
    column_mapping: Dict[str, str]
    llm_provider: str = "gemini" # gemini or openai

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
    
    # 미리보기: 첫 5행 읽기
    try:
        df = pd.read_excel(file_path, nrows=5)
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
    # 파일 찾기
    files = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(request.file_id)]
    if not files:
        raise HTTPException(status_code=404, detail="File not found.")
    
    file_path = os.path.join(UPLOAD_DIR, files[0])
    
    # Celery 작업 시작
    task = process_excel_task.delay(file_path, request.column_mapping, request.llm_provider)
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
