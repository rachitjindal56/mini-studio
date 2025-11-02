from fastapi import APIRouter, Request
from app.services.inference.controller import InferenceController
from app.services.inference.model import BaseModelDeployRequest, FineTunedDeployRequest

router = APIRouter(prefix="/inference", tags=["inference"])

controller = InferenceController()

@router.post("/deploy/base")
async def deploy_base_model(req: BaseModelDeployRequest):
    return await controller.deploy_base(req)

@router.post("/deploy/fine_tuned")
async def deploy_fine_tuned_model(req: FineTunedDeployRequest):
    return await controller.deploy_fine_tuned(req)

# handle inference requests, this is just a sample route, need to make it openai compatible to route model
@router.post("/infer/{model_name}")
async def infer(model_name: str, request: Request):
    return await controller.infer(model_name, request)