import os
import uuid
from pathlib import Path

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    HTTPException
)

from pydantic import BaseModel

from celery.result import AsyncResult

from tasks import (
    celery_app,
    process_video,
    execute_python_task,
    deploy_website
)


app = FastAPI(
    title="Heavy Task Processing API",
    description="FastAPI + Celery + Redis Backend",
    version="1.0.0"
)

UPLOAD_DIR = Path("/tmp/uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE = 500 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".mkv",
    ".webm"
}


class ScriptRequest(BaseModel):
    script_name: str


class DeployRequest(BaseModel):
    site_name: str


@app.get("/")
def home():

    return {
        "status": "online",
        "name": "Heavy Backend",
        "services": [
            "Video Processing",
            "Python Tasks",
            "Website Deployment"
        ]
    }


@app.get("/health")
def health():

    return {
        "api": "online",
        "queue": "redis/celery"
    }


# VIDEO UPLOAD

@app.post("/video/process")
async def upload_video(
    file: UploadFile = File(...)
):

    extension = Path(file.filename or "").suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported video format"
        )

    filename = f"{uuid.uuid4().hex}{extension}"
    destination = UPLOAD_DIR / filename

    size = 0

    try:
        with destination.open("wb") as output:

            while True:
                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                size += len(chunk)

                if size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File too large"
                    )

                output.write(chunk)

    except Exception:
        destination.unlink(missing_ok=True)
        raise

    finally:
        await file.close()

    task = process_video.delay(filename)

    return {
        "status": "queued",
        "task_id": task.id,
        "filename": filename
    }


# PYTHON TASK

@app.post("/python/execute")
def run_python_task(request: ScriptRequest):

    allowed = {
        "system_information",
        "generate_report"
    }

    if request.script_name not in allowed:
        raise HTTPException(
            status_code=403,
            detail="Script not authorized"
        )

    task = execute_python_task.delay(
        request.script_name
    )

    return {
        "status": "queued",
        "task_id": task.id
    }


# WEBSITE DEPLOYMENT

@app.post("/website/deploy")
def deploy(request: DeployRequest):

    if not request.site_name.replace(
        "_", ""
    ).replace("-", "").isalnum():

        raise HTTPException(
            status_code=400,
            detail="Invalid website name"
        )

    task = deploy_website.delay(
        request.site_name
    )

    return {
        "status": "queued",
        "task_id": task.id
    }


# TASK STATUS

@app.get("/task/{task_id}")
def get_task_status(task_id: str):

    task = AsyncResult(
        task_id,
        app=celery_app
    )

    response = {
        "task_id": task_id,
        "state": task.state
    }

    if task.state == "SUCCESS":
        response["result"] = task.result

    elif task.state == "FAILURE":
        response["error"] = str(task.result)

    elif task.state == "PROGRESS":
        response["progress"] = task.info

    return response


@app.get("/tasks")
def task_info():

    return {
        "message": "Use /task/{task_id} to check a job"
    }
