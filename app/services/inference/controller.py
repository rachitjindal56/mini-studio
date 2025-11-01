from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from app.services.inference.service import InferenceService
import logging

logger = logging.getLogger(__name__)

class InferenceController:
    def __init__(self):
        self.service = InferenceService()

    async def deploy_base(self, req):
        try:
            return await self.service.deploy_base_model(req)
        except Exception as e:
            logger.exception("deploy_base failed")
            raise HTTPException(status_code=500, detail=str(e))

    async def deploy_fine_tuned(self, req):
        try:
            return await self.service.deploy_fine_tuned_model(req)
        except Exception as e:
            logger.exception("deploy_fine_tuned failed")
            raise HTTPException(status_code=500, detail=str(e))

    async def infer(self, model_name: str, request: Request):
        client_code = request.headers.get("X-User-ID")
        payload = await request.json()
        try:
            return await self.service.infer_proxy(model_name, payload, client_code)
        except Exception as e:
            logger.exception("infer proxy failed")
            raise HTTPException(status_code=500, detail=str(e))