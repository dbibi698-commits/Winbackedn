import os
import shutil
import subprocess
import re
import json
from pathlib import Path

from celery import Celery

REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://localhost:6379/0"
)

celery_app = Celery(
    "heavy_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    result_expires=3600,
    worker_prefetch_multiplier=1,
    task_acks_late=True
)

UPLOAD_DIR = Path("/app/uploads")
OUTPUT_DIR = Path("/app/processed")
SITES_DIR = Path("/app/sites")
DEPLOY_DIR = Path("/app/deployed")

for folder in [UPLOAD_DIR, OUTPUT_DIR, DEPLOY_DIR]:
    folder.mkdir(parents=True, exist_ok=True)


# VIDEO PROCESSING

@celery_app.task(bind=True)
def process_video(self, filename):

    source = UPLOAD_DIR / filename
    output = OUTPUT_DIR / f"{source.stem}_processed.mp4"

    if not source.is_file():
        raise FileNotFoundError("Video not found")

    self.update_state(
        state="PROCESSING",
        meta={"progress": 10}
    )

    command = [
        "ffmpeg",
        "-y",
        "-i", str(source),
        "-vf", "scale=1280:-2",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-c:a", "aac",
        "-movflags", "+faststart",
        str(output)
    ]

    self.update_state(
        state="PROCESSING",
        meta={"progress": 30}
    )

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=3600,
        check=False
    )

    if result.returncode != 0:
        raise RuntimeError("Video processing failed")

    return {
        "status": "completed",
        "output": output.name,
        "path": str(output)
    }


# SAFE PYTHON TASK EXECUTION

def system_information():
    import platform

    return {
        "python": platform.python_version(),
        "system": platform.system(),
        "architecture": platform.machine()
    }


def generate_report():
    return {
        "status": "success",
        "message": "Report generated successfully"
    }


ALLOWED_SCRIPTS = {
    "system_information": system_information,
    "generate_report": generate_report
}


@celery_app.task(bind=True)
def execute_python_task(self, script_name):

    if script_name not in ALLOWED_SCRIPTS:
        raise ValueError("Script is not authorized")

    self.update_state(
        state="PROCESSING",
        meta={"progress": 50}
    )

    result = ALLOWED_SCRIPTS[script_name]()

    return {
        "status": "completed",
        "script": script_name,
        "result": result
    }


# STATIC WEBSITE DEPLOYMENT

@celery_app.task(bind=True)
def deploy_website(self, site_name):

    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,50}", site_name):
        raise ValueError("Invalid website name")

    source = (SITES_DIR / site_name).resolve()
    destination = (DEPLOY_DIR / site_name).resolve()

    if source.parent != SITES_DIR.resolve():
        raise ValueError("Invalid source directory")

    if not source.is_dir():
        raise FileNotFoundError("Website directory not found")

    if not (source / "index.html").is_file():
        raise ValueError("index.html is required")

    self.update_state(
        state="PROCESSING",
        meta={"progress": 50}
    )

    temp = DEPLOY_DIR / f".{site_name}_temporary"

    if temp.exists():
        shutil.rmtree(temp)

    shutil.copytree(
        source,
        temp
    )

    if destination.exists():
        shutil.rmtree(destination)

    temp.rename(destination)

    return {
        "status": "deployed",
        "website": site_name,
        "location": str(destination)
    }