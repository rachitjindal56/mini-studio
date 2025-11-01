from huggingface_hub import dataset_info
from pydantic import BaseModel


class FineTuningJobRequest(BaseModel):
    model: str
    n_epochs: int
    batch_size: int
    client_code: str
    dataset_filename: str
    prompt_loss_weight: float
    learning_rate_multiplier: float