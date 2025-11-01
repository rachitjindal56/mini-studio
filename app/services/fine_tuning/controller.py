import uuid
from fastapi.responses import JSONResponse
from app.services.fine_tuning.service import FineTuningService


class FinetuneController:
    def __init__(self):
        self.fine_tuning_service = FineTuningService()

    async def uuid_generator(self,) -> str:
        return str(uuid.uuid4())
    
    async def cluster_status(self) -> JSONResponse:
        return await self.fine_tuning_service.get_cluster_status()
    
    async def status_job_id(self, job_id) -> JSONResponse:
        res = await self.fine_tuning_service.get_job_status(job_id)
        return res
    
    async def list_jobs(self, client_code) -> JSONResponse:
        res = await self.fine_tuning_service.list_jobs(client_code)
        return res
    
    async def submit_fine_tuning_job(self, fine_tuning_params) -> JSONResponse:
        return await self.fine_tuning_service.submit_job(fine_tuning_params)
    
    async def upload_dataset(self, file, client_code: str) -> JSONResponse:
        return await self.fine_tuning_service.upload_dataset(file, client_code)