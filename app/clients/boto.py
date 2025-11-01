import boto3
from typing import Optional
from configs.envs import env_variables


class S3ClientConfig:
    _instance = None

    def __new__(cls) -> 'S3ClientConfig':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_is_initialized") and self._is_initialized:
            return
        self._is_initialized = True

        self.client: Optional[boto3.client] = None
        self.aws_access_key_id = env_variables.AWS_ACCESS_KEY_ID
        self.aws_secret_access_key = env_variables.AWS_SECRET_ACCESS_KEY
        self.aws_region = env_variables.AWS_REGION
        self.bucket_name = env_variables.AWS_BUCKET_NAME

        self._create_client()

    def _create_client(self):
        try:
            self.client = boto3.client(
                "s3",
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                region_name=self.aws_region,
            )
            print(f"S3 client initialized for bucket: {self.bucket_name}")
        except Exception as e:
            print(f"Failed to initialize S3 client: {e}")
            raise e

    def upload_file(self, file_path: str, key: str):
        if self.client is None:
            self._create_client()
        try:
            self.client.upload_file(file_path, self.bucket_name, key)
            print(f"Uploaded {file_path} to s3://{self.bucket_name}/{key}")
        except Exception as e:
            print(f"Failed to upload file to S3: {e}")
            raise e

    def download_file(self, key: str, file_path: str):
        if self.client is None:
            self._create_client()
        try:
            self.client.download_file(self.bucket_name, key, file_path)
            print(f"Downloaded s3://{self.bucket_name}/{key} to {file_path}")
        except Exception as e:
            print(f"Failed to download file from S3: {e}")
            raise e

    def get_client(self) -> boto3.client:
        if self.client is None:
            self._create_client()
        return self.client


s3_client = S3ClientConfig()