from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage, default_storage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateUploadStorage(FileSystemStorage):
    """Store uploads outside MEDIA_ROOT and read legacy files during migration."""

    def __init__(self):
        super().__init__(location=settings.PRIVATE_MEDIA_ROOT)

    def path(self, name):
        private_path = super().path(name)
        if Path(private_path).is_file():
            return private_path
        return default_storage.path(name)

    def _open(self, name, mode="rb"):
        private_path = super().path(name)
        if Path(private_path).is_file():
            return super()._open(name, mode)
        return default_storage.open(name, mode)
