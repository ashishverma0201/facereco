from io import BytesIO
from pathlib import PurePath
import zipfile
import zlib

from PIL import Image, UnidentifiedImageError
from django.core.exceptions import ValidationError


MAX_FACE_IMAGE_BYTES = 5 * 1024 * 1024
MAX_FACE_IMAGE_PIXELS = 12_000_000
MAX_HOMEWORK_FILE_BYTES = 10 * 1024 * 1024
HOMEWORK_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".png", ".jpg", ".jpeg"}


def validate_image_upload(upload):
    extension = PurePath(upload.name).suffix.lower()
    content = upload.read(MAX_FACE_IMAGE_BYTES + 1)
    upload.seek(0)
    validate_image_bytes(content, extension)


def validate_image_bytes(content, declared_extension, *, max_bytes=MAX_FACE_IMAGE_BYTES):
    if not content or len(content) > max_bytes:
        limit_mb = max(1, max_bytes // (1024 * 1024))
        raise ValidationError(f"Image must be non-empty and no larger than {limit_mb} MB.")

    extension = PurePath("upload" + declared_extension.lower()).suffix
    expected_formats = {
        ".jpg": {"JPEG"},
        ".jpeg": {"JPEG"},
        ".png": {"PNG"},
        ".webp": {"WEBP"},
    }
    if extension not in expected_formats:
        raise ValidationError("This image type is not allowed.")

    try:
        with Image.open(BytesIO(content)) as image:
            if image.format not in expected_formats[extension]:
                raise ValidationError("The image contents do not match the file type.")
            width, height = image.size
            if width < 1 or height < 1 or width * height > MAX_FACE_IMAGE_PIXELS:
                raise ValidationError("Image dimensions exceed the allowed limit.")
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationError("The uploaded image is invalid or damaged.") from exc


def validate_homework_upload(upload):
    """Validate extension, actual file signature, structure, and bounded size."""
    extension = PurePath(upload.name).suffix.lower()
    if extension not in HOMEWORK_EXTENSIONS:
        raise ValidationError("This file type is not allowed.")
    if upload.size < 1 or upload.size > MAX_HOMEWORK_FILE_BYTES:
        raise ValidationError("Files must be non-empty and no larger than 10 MB.")

    content = upload.read(MAX_HOMEWORK_FILE_BYTES + 1)
    upload.seek(0)
    if len(content) != upload.size or len(content) > MAX_HOMEWORK_FILE_BYTES:
        raise ValidationError("The uploaded file size is invalid.")

    if extension in {".jpg", ".jpeg", ".png"}:
        validate_image_bytes(content, extension, max_bytes=MAX_HOMEWORK_FILE_BYTES)
        return

    if extension == ".pdf":
        if not content.startswith(b"%PDF-") or b"%%EOF" not in content[-2048:]:
            raise ValidationError("The PDF file contents are invalid.")
        return

    if extension == ".doc":
        if not content.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
            raise ValidationError("The Word document contents are invalid.")
        return

    if extension == ".docx":
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                names = set(archive.namelist())
                if (
                    "[Content_Types].xml" not in names
                    or "word/document.xml" not in names
                    or any(name.lower().endswith("vbaproject.bin") for name in names)
                    or len(names) > 10000
                    or sum(entry.file_size for entry in archive.infolist()) > 40 * 1024 * 1024
                    or archive.testzip() is not None
                ):
                    raise ValidationError("The Word document contents are invalid or macro-enabled.")
        except (zipfile.BadZipFile, OSError, RuntimeError, EOFError, zlib.error) as exc:
            raise ValidationError("The Word document contents are invalid.") from exc
        return

    if b"\x00" in content:
        raise ValidationError("Text files must contain valid text, not binary content.")
    try:
        content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError("Text files must use UTF-8 encoding.") from exc
