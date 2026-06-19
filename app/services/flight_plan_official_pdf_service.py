from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status

from app.models.flight_plan import FlightPlan
from app.pdf.eana_flight_plan_pdf_generator import EanaFlightPlanPdfGenerator
from app.pdf.map_flight_plan_to_pdf_data import map_flight_plan_to_pdf_data
from app.services.flight_plan_signature_service import FlightPlanSignatureService
from app.services.object_storage_service import ObjectStorageService

PRESIGN_EXPIRES_SECONDS = 3600


class FlightPlanOfficialPdfService:
    def __init__(
        self,
        *,
        storage: ObjectStorageService | None = None,
        signature_service: FlightPlanSignatureService | None = None,
        pdf_generator: EanaFlightPlanPdfGenerator | None = None,
    ) -> None:
        self._storage = storage or ObjectStorageService()
        self._signature_service = signature_service or FlightPlanSignatureService(storage=self._storage)
        self._pdf_generator = pdf_generator or EanaFlightPlanPdfGenerator()

    def _ensure_storage_available(self) -> None:
        if not self._storage.is_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Object storage is not configured",
            )

    @staticmethod
    def official_pdf_key(*, flight_plan_id: UUID) -> str:
        return f"flight-plans/{flight_plan_id}/official-eana.pdf"

    @staticmethod
    def is_managed_storage_key(value: str) -> bool:
        return value.startswith("flight-plans/") and value.endswith("/official-eana.pdf")

    def _load_signature_png(self, plan: FlightPlan) -> bytes:
        stored_signature = plan.signature_url
        if stored_signature is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Flight plan signature is required to generate official PDF",
            )
        if stored_signature.startswith("http://") or stored_signature.startswith("https://"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Legacy signature URLs cannot be used for official PDF generation",
            )
        if not self._storage.object_exists(key=stored_signature):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Flight plan signature was not uploaded",
            )
        return self._storage.get_object_bytes(key=stored_signature)

    def generate_and_store(self, plan: FlightPlan) -> str:
        self._ensure_storage_available()
        signature_png_bytes = self._load_signature_png(plan)
        pdf_data = map_flight_plan_to_pdf_data(plan, signature_png_bytes=signature_png_bytes)
        pdf_bytes = self._pdf_generator.generate(pdf_data)
        object_key = self.official_pdf_key(flight_plan_id=plan.id)
        self._storage.put_object(
            key=object_key,
            body=pdf_bytes,
            content_type="application/pdf",
        )
        return object_key

    def resolve_public_official_pdf_url(self, *, stored_value: str | None) -> str | None:
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
