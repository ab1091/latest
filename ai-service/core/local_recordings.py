"""
Local-disk cache of call recordings.

The recording itself is uploaded by Vapi straight into Azure Blob Storage
(core/azure_storage.py handles signing playback URLs for that copy) — this
module additionally pulls a real copy down onto this machine's own disk,
under local_recordings/, so playback never depends on Azure being reachable
and the actual audio file genuinely lives on this project's own filesystem,
not only in the cloud.

Files are named "{Lead Name}__{call_id}.wav" when a lead name is known (so
the folder is browsable by name in Finder), or just "{call_id}.wav"
otherwise. call_id is always the suffix, so lookups by call_id alone (the
only thing callers like the /recording endpoint have) work via a glob.
"""
import glob
import logging
import os
import re

import httpx

from core.azure_storage import is_azure_blob_url, generate_sas_url

logger = logging.getLogger(__name__)

RECORDINGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "local_recordings")

_UNSAFE_CHARS = re.compile(r'[^A-Za-z0-9 _-]')
_PLACEHOLDER_NAMES = {"null", "none", "undefined", "n/a", "na"}


def _sanitize(name: str) -> str:
    cleaned = _UNSAFE_CHARS.sub("", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)[:60]
    if cleaned.lower() in _PLACEHOLDER_NAMES:
        return ""
    return cleaned


def local_path(call_id: str, lead_name: str | None = None) -> str:
    """Path to use when WRITING a new file (name-prefixed if lead_name given)."""
    if lead_name:
        safe = _sanitize(lead_name)
        if safe:
            return os.path.join(RECORDINGS_DIR, f"{safe}__{call_id}.wav")
    return os.path.join(RECORDINGS_DIR, f"{call_id}.wav")


def find_local_path(call_id: str) -> str | None:
    """Path to use when READING — finds the file regardless of whether it
    has a lead-name prefix, since callers only ever have the call_id."""
    matches = glob.glob(os.path.join(RECORDINGS_DIR, f"*{call_id}.wav"))
    return matches[0] if matches else None


def has_local_copy(call_id: str) -> bool:
    return find_local_path(call_id) is not None


async def save_locally(call_id: str, recording_url: str, lead_name: str | None = None) -> str | None:
    """Downloads the real audio bytes for a finished call and writes them to
    local_recordings/. Returns the local path, or None if the recording
    isn't fetchable (no Azure creds locally, blob not ready yet, network
    error, etc.) — best-effort, never raises."""
    if not recording_url:
        return None
    try:
        fetch_url = recording_url
        if is_azure_blob_url(recording_url):
            signed = generate_sas_url(recording_url)
            if not signed:
                logger.warning(f"[local_recordings] no Azure credentials to fetch recording for call={call_id}")
                return None
            fetch_url = signed

        os.makedirs(RECORDINGS_DIR, exist_ok=True)
        dest = local_path(call_id, lead_name)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(fetch_url)
            resp.raise_for_status()
            with open(dest, "wb") as f:
                f.write(resp.content)
        logger.info(f"[local_recordings] saved {len(resp.content)} bytes -> {dest}")
        return dest
    except Exception as e:
        logger.warning(f"[local_recordings] failed to save call={call_id}: {e}")
        return None
