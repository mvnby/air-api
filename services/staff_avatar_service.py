"""Sanitized personal photos with company-scoped, authenticated delivery."""

import hashlib
import io
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import StaffAvatar, StaffUser, TenantMembership

MAX_AVATAR_INPUT_BYTES = 5 * 1024 * 1024
MAX_AVATAR_PIXELS = 20_000_000
MAX_AVATAR_OUTPUT_BYTES = 128 * 1024


class StaffAvatarError(ValueError):
    pass


def staff_avatar_url(user: StaffUser, *, tenant_id: int) -> str | None:
    if not user.avatar_version:
        return None
    return f"/api/manager/staff/{user.id}/avatar?tenant_id={tenant_id}&v={user.avatar_version}"


def sanitize_staff_avatar(content: bytes) -> tuple[bytes, str]:
    """Decode and re-encode pixels only, discarding all user-supplied metadata."""
    if not content or len(content) > MAX_AVATAR_INPUT_BYTES:
        raise StaffAvatarError("Размер фотографии должен быть не больше 5 МБ")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"}:
                    raise StaffAvatarError("Выберите фотографию JPEG, PNG или WebP")
                if image.width * image.height > MAX_AVATAR_PIXELS:
                    raise StaffAvatarError("Разрешение фотографии слишком велико")
                if getattr(image, "is_animated", False):
                    raise StaffAvatarError("Выберите неподвижную фотографию")
                image.load()
                pixels = ImageOps.fit(
                    ImageOps.exif_transpose(image).convert("RGB"), (256, 256),
                    method=Image.Resampling.LANCZOS,
                )
                output = io.BytesIO()
                pixels.save(output, format="WEBP", quality=85, method=4)
                result = output.getvalue()
    except StaffAvatarError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise StaffAvatarError("Не удалось прочитать фотографию") from exc
    if len(result) > MAX_AVATAR_OUTPUT_BYTES:
        raise StaffAvatarError("Не удалось уменьшить фотографию")
    return result, hashlib.sha256(result).hexdigest()


class StaffAvatarService:
    @staticmethod
    async def read(
        session: AsyncSession, *, staff_user_id: int, viewer_tenant_id: int,
        is_platform_owner: bool,
    ) -> StaffAvatar | None:
        # Check access before content or conditional HTTP responses. Retained
        # memberships allow photos on historical orders after staff departure.
        statement = select(StaffUser.id).where(StaffUser.id == staff_user_id)
        if not is_platform_owner:
            statement = statement.join(
                TenantMembership, TenantMembership.staff_user_id == StaffUser.id,
            ).where(TenantMembership.tenant_id == viewer_tenant_id)
        if await session.scalar(statement) is None:
            return None
        return await session.get(StaffAvatar, staff_user_id)
