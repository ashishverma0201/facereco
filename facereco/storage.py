
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage, default_storage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateUploadStorage(FileSystemStorage):
    """Store uploads outside MEDIA_ROOT and support legacy image paths."""

    def __init__(self):
        super().__init__(location=settings.PRIVATE_MEDIA_ROOT)

    @staticmethod
    def _storage_name(name):
        """Normalize the known legacy media prefix safely."""
        name = str(name).replace("\\", "/")

        legacy_prefix = "../media/"
        if name.startswith(legacy_prefix):
            name = name[len(legacy_prefix):]

        # Reject any remaining path traversal.
        parts = Path(name).parts
        if not name or ".." in parts or name.startswith("/"):
            raise ValueError(f"Invalid image path: {name!r}")

        return name

   
    
    def path(self, name):
            name = self._storage_name(name)

            private_path = super().path(name)
            if Path(private_path).is_file():
             return private_path

            legacy_path = Path(settings.MEDIA_ROOT) / name
            if legacy_path.is_file():
             return str(legacy_path)

            return private_path


    def save(self, name, content, max_length=None):
        normalized_name = self._storage_name(name)
        return super().save(
            normalized_name,
            content,
            max_length=max_length,
        )

    

def open(self, name, mode="rb"):
    name = self._storage_name(name)

    private_path = super().path(name)
    if Path(private_path).is_file():
        return super()._open(name, mode)

    legacy_path = Path(settings.MEDIA_ROOT) / name
    if legacy_path.is_file():
        return open(legacy_path, mode)

    raise FileNotFoundError(
        f"Image not found in private or legacy media storage: {name}"
    )

