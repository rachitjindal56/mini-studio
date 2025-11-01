from pydantic import BaseModel

class BaseModelDeployRequest(BaseModel):
    client_code: str
    model_id: str
    gpu_count: int = 1
    min_replicas: int = 1
    max_replicas: int = 2
    prometheus_threshold: int = 5


class FineTunedDeployRequest(BaseModel):
    client_code: str
    base_model: str
    fine_tuned_weights_path: str
    gpu_count: int = 1
    min_replicas: int = 1
    max_replicas: int = 2
    prometheus_threshold: int = 5