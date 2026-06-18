"""S3-compatible object storage (MinIO) client.

Object key convention (for future uploads):
    aircraft/{aircraft_id}/{uuid}.{ext}
"""

from __future__ import annotations

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import Settings, settings as default_settings


class ObjectStorageService:
    def __init__(
        self,
        *,
        app_settings: Settings | None = None,
        s3_client: BaseClient | None = None,
    ) -> None:
        self._settings = app_settings or default_settings
        self._s3_client = s3_client

    def is_configured(self) -> bool:
        return self._settings.s3_configured

    def _get_client(self) -> BaseClient:
        if self._s3_client is not None:
            return self._s3_client

        return boto3.client(
            "s3",
            endpoint_url=self._settings.S3_ENDPOINT_URL,
            aws_access_key_id=self._settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=self._settings.S3_SECRET_ACCESS_KEY,
            region_name=self._settings.S3_REGION,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        )

    def _ensure_configured(self) -> None:
        if not self.is_configured():
            raise RuntimeError("Object storage is not configured")

    def put_object(self, *, key: str, body: bytes, content_type: str) -> str:
        self._ensure_configured()
        client = self._get_client()
        client.put_object(
            Bucket=self._settings.S3_BUCKET_NAME,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
        return key

    def delete_object(self, *, key: str) -> None:
        self._ensure_configured()
        client = self._get_client()
        client.delete_object(Bucket=self._settings.S3_BUCKET_NAME, Key=key)

    def object_exists(self, *, key: str) -> bool:
        self._ensure_configured()
        client = self._get_client()
        try:
            client.head_object(Bucket=self._settings.S3_BUCKET_NAME, Key=key)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True

    def generate_presigned_put_url(
        self,
        *,
        key: str,
        content_type: str,
        expires_in: int = 3600,
    ) -> str:
        self._ensure_configured()
        client = self._get_client()
        return client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": self._settings.S3_BUCKET_NAME,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )

    def generate_presigned_get_url(self, *, key: str, expires_in: int = 3600) -> str:
        self._ensure_configured()
        client = self._get_client()
        return client.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": self._settings.S3_BUCKET_NAME,
                "Key": key,
            },
            ExpiresIn=expires_in,
        )
