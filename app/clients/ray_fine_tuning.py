import ray
from ray.job_submission import JobSubmissionClient
from typing import Optional, Any, Dict
from configs.envs import env_variables
import logging

logger = logging.getLogger(__name__)


class RayClientConfig:
    _instance = None

    def __new__(cls) -> 'RayClientConfig':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_is_initialized") and self._is_initialized:
            return
        self._is_initialized = True

        self.client = None
        self.ray_address = getattr(env_variables, "RAY_HEAD_ADDRESS", None)
        self._connect_client()

    def _connect_client(self):
        try:
            # If ray is already initialized, don't call init again.
            if ray.is_initialized():
                logger.info("Ray already initialized")
                self.client = ray
                return

            if self.ray_address:
                ray.init(address=self.ray_address)
            else:
                ray.init()
            self.client = ray
            logger.info("Connected to Ray cluster at %s", self.ray_address or "local")
        except Exception as e:
            logger.exception("Failed to initialize Ray client: %s", e)
            self.client = None

    def get_client(self):
        if self.client is None:
            self._connect_client()
        return self.client

    def submit_job(self, entrypoint: str, runtime_env: Dict[str, Any] = None) -> Optional[str]:
        """
        Submit a job using Ray Job API (best-effort). Returns job id or None on failure.
        :param entrypoint: command to run (e.g., "python train.py ...")
        :param runtime_env: optional runtime env dict
        """
        try:
            if self.client is None:
                self._connect_client()
            if self.client is None:
                raise RuntimeError("Ray client not available")

            job_id = None
            try:
                client = JobSubmissionClient(self.ray_address)
                job_id = client.submit_job(entrypoint=entrypoint, runtime_env=runtime_env or {})
            except Exception:
                @ray.remote
                def _task(cmd):
                    import subprocess, os
                    try:
                        subprocess.check_call(cmd, shell=True)
                        return {"status": "ok"}
                    except Exception as e:
                        return {"status": "failed", "error": str(e)}

                ref = _task.remote(entrypoint)
                job_id = str(ref)
            logger.info("Submitted Ray job, id=%s", job_id)
            return job_id
        except Exception as e:
            logger.exception("submit_job failed: %s", e)
            return None

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Try to fetch status for a Ray job. Return dict with at least 'status' key.
        This is best-effort and will differ across Ray versions.
        """
        try:
            if self.client is None:
                self._connect_client()
            if self.client is None:
                return {"status": "ray_unavailable"}

            try:
                try:
                    client = JobSubmissionClient(self.ray_address)
                    info = client.get_job_status(job_id)
                    return {"status": getattr(info, "status", "unknown"), "raw": info}
                except Exception:
                    return {"status": "unknown", "info": "cannot determine status for this Ray version/job id"}
            except Exception as e:
                logger.debug("get_job_status fallback path: %s", e)
                return {"status": "unknown", "error": str(e)}
        except Exception as e:
            logger.exception("get_job_status failed: %s", e)
            return {"status": "error", "error": str(e)}

    def get_cluster_resources(self) -> Dict[str, Any]:
        try:
            if self.client is None:
                self._connect_client()
            if self.client is None:
                return {"status": "ray_unavailable"}

            total = ray.cluster_resources()
            available = {}
            try:
                available = ray.available_resources()
            except Exception:
                # some Ray versions don't provide available_resources
                available = total
            return {"status": "healthy", "total_resources": total, "available_resources": available}
        except Exception as e:
            logger.exception("get_cluster_resources failed: %s", e)
            return {"status": "error", "error": str(e)}


ray_client = RayClientConfig()