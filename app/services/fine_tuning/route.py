from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse
from app.services.fine_tuning.controller import FinetuneController
from app.services.fine_tuning.model import FineTuningJobRequest

router = APIRouter(
    prefix="/fine_tuning",
    tags=["fine_tuning"]
)

fine_tuning_controller = FinetuneController()

# API: Get Cluster Status
@router.get("/cluster-status")
async def check_cluster_status() -> JSONResponse:
    return await fine_tuning_controller.cluster_status()

# API: List All Jobs
@router.get("/jobs/client/{client_code}")
async def list_jobs(client_code: str) -> JSONResponse:
    return await fine_tuning_controller.list_jobs(client_code)

# API: Get Job Status
@router.get("/jobs/{job_id}")
async def job_status(job_id: str) -> JSONResponse:
    return await fine_tuning_controller.status_job_id(job_id)

# API: Submit Fine-tuning Job
@router.post("/submit-finetune")
async def submit_fineuning_job(request: FineTuningJobRequest) -> JSONResponse:
    return await fine_tuning_controller.submit_fine_tuning_job(request)

# API: Upload dataset separately (stores to DFS and S3)
@router.post("/upload-dataset/{client_code}")
async def upload_dataset(client_code: str, file: UploadFile = File(...)) -> JSONResponse:
    return await fine_tuning_controller.upload_dataset(file, client_code)