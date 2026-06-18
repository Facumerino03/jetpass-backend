from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import HTTPException, status

from app.models.flight_plan import FlightPlan
from app.services.object_storage_service import ObjectStorageService

SIGNATURE_CONTENT_TYPE = "image/png"
PRESIGN_EXPIRES_SECONDS = 3600


class FlightPlanSignatureService:
    def __init__(self, *, storage: ObjectStorageService | None = None) -> None:
        self._storage = storage or ObjectStorageService()

    def _ensure_storage_available(self) -> None:
        if not self._storage.is_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Object storage is not configured",
            )

    @staticmethod
    def signature_key(*, flight_plan_id: UUID) -> str:
        return f"flight-plans/{flight_plan_id}/{uuid4()}.png"

    @staticmethod
    def is_signature_key_for_plan(*, signature_key: str, flight_plan_id: UUID) -> bool:
        prefix = f"flight-plans/{flight_plan_id}/"
        return signature_key.startswith(prefix)

    @staticmethod
    def is_managed_storage_key(signature_key: str) -> bool:
        return signature_key.startswith("flight-plans/")

    def presign_for_plan(self, *, plan: FlightPlan, content_type: str) -> dict[str, str | int]:
        self._ensure_storage_available()
        if content_type != SIGNATURE_CONTENT_TYPE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported signature content type",
            )

        signature_key = self.signature_key(flight_plan_id=plan.id)
        upload_url = self._storage.generate_presigned_put_url(
            key=signature_key,
            content_type=content_type,
            expires_in=PRESIGN_EXPIRES_SECONDS,
        )
        return {
            "upload_url": upload_url,
            "signature_key": signature_key,
            "expires_in": PRESIGN_EXPIRES_SECONDS,
        }

    def validate_signature_key_for_plan(self, *, plan: FlightPlan, signature_key: str) -> str:
        self._ensure_storage_available()
        if not self.is_signature_key_for_plan(signature_key=signature_key, flight_plan_id=plan.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid flight plan signature key",
            )
        if not self._storage.object_exists(key=signature_key):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Flight plan signature was not uploaded",
            )
        return signature_key

    def resolve_public_signature_url(self, *, stored_value: str | None) -> str | None:
        if stored_value is None:
            return None
        if stored_value.startswith("http://") or stored_value.startswith("https://"):
            return stored_value
        if not self._storage.is_configured():
            return None
        if not self._storage.object_exists(key=stored_value):
            return None
        return self._storage.generate_presigned_get_url(
            key=stored_value,
            expires_in=PRESIGN_EXPIRES_SECONDS,
        )

    def delete_managed_signature_if_present(self, *, stored_value: str | None) -> None:
        if stored_value is None or not self.is_managed_storage_key(stored_value):
            return
        if not self._storage.is_configured():
            return
        if self._storage.object_exists(key=stored_value):
            self._storage.delete_object(key=stored_value)
