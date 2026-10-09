from datetime import datetime
from pydantic import BaseModel, ConfigDict


class RegistrationCertificateItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    legal_entity_id: int
    filename: str
    mime_type: str
    checksum_sha256: str
    size_bytes: int
    is_current: bool
    created_at: datetime
