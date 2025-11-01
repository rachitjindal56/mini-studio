from contextlib import asynccontextmanager
from math import inf

import opik
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from app.services.fine_tuning import route as fine_tuning_router
from app.services.inference import route as inference_router


from configs.envs import env_variables
from app.database.mongo import mongodb
from app.database.redis import client_config
from app.middleware.logger.logging import LoggingMiddleware, RequestResponseLogger


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Connecting to MongoDB...........................")
    await mongodb.connect_to_database()
    await client_config.check_connection()
    yield
    # Shutdown
    await mongodb.close_database_connection()
    await client_config.close_connection()


request_response_logger = RequestResponseLogger()

app = FastAPI(title="Mini Studio Fine-tuning Backend",lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(LoggingMiddleware, request_response_logger=request_response_logger)


@app.get("/")
async def root():
    return {"message": "Welcome to Mini Studio Backend!"}

@app.get("/health")
async def health_check():
    return {"status": 200, "message": "OK"}

app.include_router(fine_tuning_router)
app.include_router(inference_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(env_variables.PORT))