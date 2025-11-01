import os
import uuid
import time
import asyncio
import tempfile
import shutil
import logging
from typing import Dict, Any, Optional, Tuple, List

import boto3
from fastapi.responses import JSONResponse
from fastapi import UploadFile

logger = logging.getLogger(__name__)

try:
    from configs.envs import env_variables
    AWS_BUCKET = getattr(env_variables, "AWS_BUCKET_NAME", os.environ.get("AWS_BUCKET_NAME"))
    DFS_BASE = getattr(env_variables, "DFS_BASE_PATH", os.environ.get("DFS_BASE_PATH", "/tmp/mini-studio-dfs"))
except Exception:
    AWS_BUCKET = os.environ.get("AWS_BUCKET_NAME")
    DFS_BASE = os.environ.get("DFS_BASE_PATH", "/tmp/mini-studio-dfs")

try:
    from app.clients.boto import s3_client as project_s3_client
except Exception:
    project_s3_client = None

_boto3_client = boto3.client("s3")

try:
    from app.clients.ray_fine_tuning import ray_client
except Exception:
    ray_client = None

try:
    from app.database.mongo import mongodb
except Exception:
    mongodb = None


class FineTuningService:
    """
    Service that persists fine-tuning jobs to MongoDB (via app.database.mongo.mongodb),
    stores datasets to DFS and S3, and submits jobs to Ray (via app.clients.ray_fine_tuning.ray_client) when available.
    """

    def __init__(self) -> None:
        self._jobs_cache: Dict[str, Dict[str, Any]] = {}

        self._jobs_coll = None
        self._db = None
        self._mongo = None

        try:
            if mongodb is not None:
                self._db = mongodb.get_database()
                self._jobs_coll = self._db.get_collection("fine_tuning_jobs")
                try:
                    asyncio.get_event_loop().create_task(self._ensure_indexes())
                except Exception:
                    pass
                logger.info("Using MongoDB from app.database.mongo for fine_tuning_jobs collection")
        except Exception:
            logger.exception("Failed to initialize MongoDB for fine tuning service")
            self._mongo = None
            self._db = None
            self._jobs_coll = None

    async def _ensure_indexes(self):
        try:
            if self._jobs_coll is not None:
                await self._jobs_coll.create_index("job_id", unique=True)
        except Exception:
            logger.exception("Failed to create index on jobs collection")

    async def _insert_job(self, job: Dict[str, Any]) -> None:
        if self._jobs_coll is not None:
            try:
                await self._jobs_coll.insert_one(job)
                return
            except Exception:
                logger.exception("Failed to insert job into MongoDB, falling back to cache")
        self._jobs_cache[job["job_id"]] = job

    async def _update_job(self, job_id: str, update: Dict[str, Any]) -> None:
        if self._jobs_coll is not None:
            try:
                await self._jobs_coll.update_one({"job_id": job_id}, {"$set": update})
                return
            except Exception:
                logger.exception("Failed to update job in MongoDB, updating cache")
        job = self._jobs_cache.get(job_id)
        if job:
            job.update(update)

    async def _get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        if self._jobs_coll is not None:
            try:
                doc = await self._jobs_coll.find_one({"job_id": job_id})
                return doc
            except Exception:
                logger.exception("Failed to fetch job from MongoDB, trying cache")
        return self._jobs_cache.get(job_id)

    async def _list_jobs(self, client_code: str) -> List[Dict[str, Any]]:
        if self._jobs_coll is not None:
            try:
                cursor = self._jobs_coll.find({"client_code": client_code}).sort("created_at", -1)
                return [doc async for doc in cursor]
            except Exception:
                logger.exception("Failed to list jobs from MongoDB, using cache")
        return list(self._jobs_cache.values())

    async def get_cluster_status(self) -> JSONResponse:
        try:
            if ray_client is not None:
                res = ray_client.get_cluster_resources()
                return JSONResponse(content={"ok": True, "status": res}, status_code=200)
            status = {
                "nodes": 1,
                "gpus_total": 0,
                "gpus_available": 0,
                "status": "ray_unavailable",
                "last_checked": int(time.time())
            }
            return JSONResponse(content={"ok": True, "status": status}, status_code=200)
        except Exception as e:
            logger.exception("get_cluster_status failed")
            return JSONResponse(content={"ok": False, "error": str(e)}, status_code=500)

    async def list_jobs(self, client_code: str) -> JSONResponse:
        try:
            jobs = await self._list_jobs(client_code)
            for j in jobs:
                if isinstance(j, dict):
                    j.pop("_id", None)
            return JSONResponse(content={"ok": True, "jobs": jobs}, status_code=200)
        except Exception as e:
            logger.exception("list_jobs failed")
            return JSONResponse(content={"ok": False, "error": str(e)}, status_code=500)

    async def get_job_status(self, job_id: str) -> JSONResponse:
        try:
            job = await self._get_job(job_id)
            if job is None:
                return JSONResponse(content={"ok": False, "error": "job not found"}, status_code=404)

            ray_job_id = job.get("ray_job_id") or job.get("ray_task_id")
            if ray_client is not None and ray_job_id:
                try:
                    status = ray_client.get_job_status(ray_job_id)
                    job_status = dict(job)
                    job_status["ray_status"] = status
                    job_status.pop("_id", None)
                    return JSONResponse(content={"ok": True, "job": job_status}, status_code=200)
                except Exception:
                    logger.exception("Failed to get ray job status for %s", job_id)

            if isinstance(job, dict):
                job.pop("_id", None)
            return JSONResponse(content={"ok": True, "job": job}, status_code=200)
        except Exception as e:
            logger.exception("get_job_status failed")
            return JSONResponse(content={"ok": False, "error": str(e)}, status_code=500)

    async def _background_process_job(self, job_id: str, job: Dict[str, Any]) -> None:
        """
        Try to submit job to Ray via ray_client; otherwise simulate locally.
        Keep DB updated with status and any ray job id.
        """
        try:
            await self._update_job(job_id, {"status": "queued", "updated_at": int(time.time())})

            if ray_client is not None:
                try:
                    # Build an entrypoint with training entrypoint and args.
                    entrypoint = f"python {env_variables.FINETUNING_SCRIPT_PATH}.py --dataset {job['dataset_dfs']} --model_name {job['model_name']} --gpus {job['estimated_gpus']} --job_id {job_id}"
                    ray_job_id = ray_client.submit_job(entrypoint=entrypoint, runtime_env={"env": {}})
                    if ray_job_id:
                        await self._update_job(job_id, {"status": "running", "ray_job_id": ray_job_id, "updated_at": int(time.time())})
                        await self._update_job(job_id, {"status": "running", "updated_at": int(time.time())})
                        return
                except Exception:
                    logger.exception("Failed to submit/check Ray job, falling back to local simulation")
        except Exception as e:
            logger.exception("Error processing job %s: %s", job_id, e)
            await self._update_job(job_id, {"status": "error", "error": str(e), "updated_at": int(time.time())})

    async def _save_dataset(self, file: UploadFile, client_code: str) -> Tuple[str, Optional[str], int]:
        try:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                file.file.seek(0)
                shutil.copyfileobj(file.file, tmp)
                tmp_path = tmp.name

            dfs_dir = os.path.join(DFS_BASE, client_code, "datasets")
            os.makedirs(dfs_dir, exist_ok=True)
            filename = f"{uuid.uuid4().hex}_{os.path.basename(file.filename or 'dataset')}"
            dfs_path = os.path.join(dfs_dir, filename)

            os.replace(tmp_path, dfs_path)

            s3_key = None
            if AWS_BUCKET:
                s3_key = f"{client_code}/datasets/{filename}"
                try:
                    if project_s3_client is not None and hasattr(project_s3_client, "upload_file"):
                        project_s3_client.upload_file(dfs_path, s3_key)
                    else:
                        _boto3_client.upload_file(dfs_path, AWS_BUCKET, s3_key)
                except Exception:
                    logger.exception("S3 upload failed for %s", dfs_path)
                    s3_key = None

            size_bytes = os.path.getsize(dfs_path)
            return dfs_path, s3_key, size_bytes
        except Exception:
            logger.exception("Failed to save dataset")
            raise

    async def upload_dataset(self, file: UploadFile, client_code: str) -> JSONResponse:
        """
        Public helper to save an uploaded dataset to DFS and S3 and persist metadata to MongoDB.
        """
        try:
            dfs_path, s3_key, size_bytes = await self._save_dataset(file, client_code)

            dataset_id = None
            try:
                if self._db is not None:
                    datasets_coll = self._db.get_collection("fine_tuning_datasets")
                    dataset_doc = {
                        "client_code": client_code,
                        "filename": os.path.basename(dfs_path),
                        "dataset_dfs": dfs_path,
                        "dataset_s3": s3_key,
                        "size_bytes": size_bytes,
                        "created_at": int(time.time()),
                    }
                    insert_res = await datasets_coll.insert_one(dataset_doc)
                    dataset_id = str(insert_res.inserted_id)
            except Exception:
                logger.exception("Failed to persist dataset metadata to MongoDB; continuing without DB record")

            return JSONResponse(
                content={
                    "ok": True,
                    "dataset_id": dataset_id,
                    "dataset_dfs": dfs_path,
                    "dataset_s3": s3_key,
                    "size_bytes": size_bytes,
                },
                status_code=201,
            )
        except ValueError as e:
            return JSONResponse(content={"ok": False, "error": str(e)}, status_code=400)
        except Exception as e:
            logger.exception("upload_dataset failed")
            return JSONResponse(content={"ok": False, "error": str(e)}, status_code=500)

    async def submit_job(self, request) -> JSONResponse:
        """
        Persist job to DB and enqueue background processing (Ray if available).

        Expects request to follow FineTuningJobRequest (model.py). At submit time
        we fetch dataset metadata from the `fine_tuning_datasets` collection in
        MongoDB (dataset must have been uploaded earlier via upload_dataset).
        """
        try:
            # normalize payload (support Pydantic model, dict, or object)
            if hasattr(request, "model_dump"):
                payload = request.model_dump()
            elif hasattr(request, "dict"):
                payload = request.dict()
            elif isinstance(request, dict):
                payload = request
            else:
                payload = {k: getattr(request, k) for k in dir(request) if not k.startswith("_") and not callable(getattr(request, k))}

            model_name = payload.get("model_name")
            if not model_name:
                return JSONResponse(content={"ok": False, "error": "model (model name) is required"}, status_code=400)

            client_code = payload.get("client_code") or model_name

            dataset_identifier = payload.get("dataset_filename")
            dfs_dataset_path = None
            s3_key = None
            dataset_size = 0
            dataset_doc = None

            if isinstance(dataset_identifier, UploadFile):
                dfs_dataset_path, s3_key, dataset_size = await self._save_dataset(dataset_identifier, client_code)
                try:
                    if self._db is not None:
                        datasets_coll = self._db.get_collection("fine_tuning_datasets")
                        dataset_doc = {
                            "client_code": client_code,
                            "filename": os.path.basename(dfs_dataset_path),
                            "dataset_dfs": dfs_dataset_path,
                            "dataset_s3": s3_key,
                            "size_bytes": dataset_size,
                            "created_at": int(time.time()),
                        }
                        insert_res = await datasets_coll.insert_one(dataset_doc)
                        dataset_doc["_id"] = insert_res.inserted_id
                except Exception:
                    logger.exception("Failed to persist dataset metadata to MongoDB after saving upload")

            elif isinstance(dataset_identifier, (str, bytes)) and str(dataset_identifier).strip():
                dataset_identifier = str(dataset_identifier).strip()
                if self._db is not None:
                    try:
                        datasets_coll = self._db.get_collection("fine_tuning_datasets")
                        query_or = [
                            {"dataset_s3": dataset_identifier},
                            {"dataset_dfs": dataset_identifier},
                            {"filename": dataset_identifier},
                        ]
                        try:
                            from bson import ObjectId
                            try:
                                oid = ObjectId(dataset_identifier)
                                query_or.append({"_id": oid})
                            except Exception:
                                pass
                        except Exception:
                            pass

                        dataset_doc = await datasets_coll.find_one({"$or": query_or})
                    except Exception:
                        logger.exception("Failed to query fine_tuning_datasets collection")

                if dataset_doc:
                    dfs_dataset_path = dataset_doc.get("dataset_dfs")
                    s3_key = dataset_doc.get("dataset_s3")
                    dataset_size = dataset_doc.get("size_bytes") or dataset_doc.get("dataset_size_bytes") or 0
                else:
                    if os.path.exists(dataset_identifier):
                        dfs_dataset_path = dataset_identifier
                        try:
                            dataset_size = os.path.getsize(dfs_dataset_path)
                        except Exception:
                            dataset_size = 0
                    else:
                        return JSONResponse(
                            content={
                                "ok": False,
                                "error": "dataset not found in database and not present as local path; please upload dataset via /fine_tuning/upload-dataset first or provide a valid dataset id/path"
                            },
                            status_code=400,
                        )
            else:
                return JSONResponse(content={"ok": False, "error": "dataset_filename (or dataset_id) is required"}, status_code=400)

            # estimate resources (Asuming 48GB GPU memory L40s only)
            gpu_per_bytes = 48 * 1024 * 1024 * 1024
            estimated_gpus = max(1, (dataset_size // gpu_per_bytes) + 1)

            job_id = str(uuid.uuid4())
            now = int(time.time())
            job = {
                "job_id": job_id,
                "client_code": client_code,
                "status": "submitted",
                "created_at": now,
                "updated_at": now,
                "model_name": model_name,
                "dataset_dfs": dfs_dataset_path,
                "dataset_s3": s3_key,
                "dataset_size_bytes": dataset_size,
                "estimated_gpus": estimated_gpus,
                "request": {
                    "model": model_name,
                    "n_epochs": payload.get("n_epochs"),
                    "batch_size": payload.get("batch_size"),
                    "prompt_loss_weight": payload.get("prompt_loss_weight"),
                    "learning_rate_multiplier": payload.get("learning_rate_multiplier"),
                    "dataset_filename": payload.get("dataset_filename"),
                    "raw": payload,
                },
            }

            await self._insert_job(job)
            asyncio.create_task(self._background_process_job(job_id, job))

            return JSONResponse(content={"ok": True, "job": job}, status_code=201)
        except ValueError as e:
            return JSONResponse(content={"ok": False, "error": str(e)}, status_code=400)
        except Exception as e:
            logger.exception("submit_job failed")
            return JSONResponse(content={"ok": False, "error": str(e)}, status_code=500)
