"""
Azure Blob Storage — generates short-lived signed (SAS) URLs for call
recordings. Vapi is configured (in its own dashboard) to upload recordings
directly into our container; we never touch the upload path, only signing
for playback.
"""
import logging
from urllib.parse import urlparse, unquote

from azure.storage.blob import BlobSasPermissions, generate_blob_sas

from core.config import (AZURE_STORAGE_ACCOUNT_NAME, AZURE_STORAGE_ACCOUNT_KEY,
    AZURE_STORAGE_CONTAINER)

logger = logging.getLogger(__name__)


def is_azure_blob_url(url: str) -> bool:
    return bool(AZURE_STORAGE_ACCOUNT_NAME) and f"{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net" in (url or "")


def _blob_name_from_url(url: str) -> str | None:
    """Extract the blob path from a full Azure blob URL, e.g.
    https://audioocrm.blob.core.windows.net/call-recordings/foo/bar.wav -> foo/bar.wav
    """
    path = urlparse(url).path.lstrip("/")  # "call-recordings/foo/bar.wav"
    prefix = f"{AZURE_STORAGE_CONTAINER}/"
    if not path.startswith(prefix):
        return None
    return unquote(path[len(prefix):])


def generate_sas_url(blob_url: str, expiry_minutes: int = 60) -> str | None:
    """Given a stored (unsigned) Azure blob URL, return a freshly signed,
    time-limited playback URL. Returns None if not one of our blobs or if
    Azure credentials aren't configured."""
    if not (AZURE_STORAGE_ACCOUNT_NAME and AZURE_STORAGE_ACCOUNT_KEY):
        return None
    blob_name = _blob_name_from_url(blob_url)
    if not blob_name:
        return None

    from datetime import datetime, timedelta
    try:
        sas_token = generate_blob_sas(
            account_name=AZURE_STORAGE_ACCOUNT_NAME,
            container_name=AZURE_STORAGE_CONTAINER,
            blob_name=blob_name,
            account_key=AZURE_STORAGE_ACCOUNT_KEY,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(minutes=expiry_minutes),
        )
        return f"{blob_url}?{sas_token}"
    except Exception as e:
        logger.error(f"[azure_storage] failed to generate SAS for {blob_name}: {e}")
        return None
