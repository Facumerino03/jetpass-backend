from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import HTTPException, status

from app.models.aircraft import Aircraft
from app.models.user import User
from app.services.object_storage_service import ObjectStorageService

ALLOWED_IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
CONTENT_TYPE_TO_EXTENSION = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
PRESIGN_EXPIRES_SECONDS = 3600


class AircraftImageService:
    def __init__(self, *, storage: ObjectStorageService | None = None) -> None:
        self._storage = storage or ObjectStorageService()

    def _ensure_storage_available(self) -> None:
        if not self._storage.is_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Object storage is not configured",
            )

    @staticmethod
    def _extension_for_content_type(content_type: str) -> str:
        extension = CONTENT_TYPE_TO_EXTENSION.get(content_type)
        if extension is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported image content type",
            )
        return extension

    @staticmethod
    def pending_image_key(*, user_id: UUID, content_type: str) -> str:
        extension = AircraftImageService._extension_for_content_type(content_type)
        return f"aircraft/pending/{user_id}/{uuid4()}.{extension}"

    @staticmethod
    def aircraft_image_key(*, aircraft_id: UUID, content_type: str) -> str:
        extension = AircraftImageService._extension_for_content_type(content_type)
        return f"aircraft/{aircraft_id}/{uuid4()}.{extension}"

    @staticmethod
    def is_pending_key_for_user(*, image_key: str, user_id: UUID) -> bool:
        prefix = f"aircraft/pending/{user_id}/"
        return image_key.startswith(prefix)

    @staticmethod
    def is_aircraft_key_for_aircraft(*, image_key: str, aircraft_id: UUID) -> bool:
        prefix = f"aircraft/{aircraft_id}/"
        return image_key.startswith(prefix)

    @staticmethod
    def is_managed_storage_key(image_key: str) -> bool:
        return image_key.startswith("aircraft/")

    @staticmethod
    def final_key_from_pending(*, pending_key: str, aircraft_id: UUID) -> str:
        filename = pending_key.rsplit("/", 1)[-1]
        return f"aircraft/{aircraft_id}/{filename}"

    def presign_for_create(self, *, current_user: User, content_type: str) -> dict[str, str | int]:
        self._ensure_storage_available()
        if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported image content type",
            )

        image_key = self.pending_image_key(user_id=current_user.id, content_type=content_type)
        upload_url = self._storage.generate_presigned_put_url(
            key=image_key,
            content_type=content_type,
            expires_in=PRESIGN_EXPIRES_SECONDS,
        )
        return {
            "upload_url": upload_url,
            "image_key": image_key,
            "expires_in": PRESIGN_EXPIRES_SECONDS,
        }

    def presign_for_aircraft(
        self,
        *,
        aircraft: Aircraft,
        content_type: str,
    ) -> dict[str, str | int]:
        self._ensure_storage_available()
        if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported image content type",
            )

        image_key = self.aircraft_image_key(aircraft_id=aircraft.id, content_type=content_type)
        upload_url = self._storage.generate_presigned_put_url(
            key=image_key,
            content_type=content_type,
            expires_in=PRESIGN_EXPIRES_SECONDS,
        )
        return {
            "upload_url": upload_url,
            "image_key": image_key,
            "expires_in": PRESIGN_EXPIRES_SECONDS,
        }

    def validate_image_key_for_create(self, *, current_user: User, image_key: str) -> str:
        self._ensure_storage_available()
        if not self.is_pending_key_for_user(image_key=image_key, user_id=current_user.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid aircraft image key",
            )
        if not self._storage.object_exists(key=image_key):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Aircraft image was not uploaded",
            )
        return image_key

    def validate_image_key_for_update(
        self,
        *,
        aircraft: Aircraft,
        image_key: str,
    ) -> str:
        self._ensure_storage_available()
        if not self.is_aircraft_key_for_aircraft(image_key=image_key, aircraft_id=aircraft.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid aircraft image key",
            )
        if not self._storage.object_exists(key=image_key):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Aircraft image was not uploaded",
            )
        return image_key

    def finalize_pending_image(self, *, pending_key: str, aircraft_id: UUID) -> str:
        final_key = self.final_key_from_pending(pending_key=pending_key, aircraft_id=aircraft_id)
        return self._storage.move_object(source_key=pending_key, dest_key=final_key)

    def resolve_public_image_url(self, *, stored_value: str | None) -> str | None:
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

    def delete_managed_image_if_present(self, *, stored_value: str | None) -> None:
        if stored_value is None or not self.is_managed_storage_key(stored_value):
            return
        if not self._storage.is_configured():
            return
        if self._storage.object_exists(key=stored_value):
            self._storage.delete_object(key=stored_value)
