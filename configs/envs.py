import os
from enum import Enum
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

class APP_ENV(Enum):
    dev = ".env"
    testing = ".test.env"
    staging = ".staging.env"
    prod = ".prod.env"

# Default to 'dev' if no env variable set
environment = os.getenv('APP_ENV', 'prod')

# Load the appropriate .env file based on the environment
dotenv_file = f'{APP_ENV[environment].value}'
load_dotenv(dotenv_path=dotenv_file)
print(f"LOADED ENV FILE: {dotenv_file}")

class Settings(BaseSettings):
    DATABASE_NAME: str
    MONGODB_URL: str
    AWS_BUCKET_NAME: str
    AWS_REGION: str
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_PASSWORD: Optional[str] = None
    REDIS_USERNAME: Optional[str] = None
    DATASTORE_ID: str
    PORT: int
    DFS_BASE_PATH: str
    FINETUNING_SCRIPT_PATH: str
    model_config = SettingsConfigDict(env_file=dotenv_file)

env_variables = Settings()