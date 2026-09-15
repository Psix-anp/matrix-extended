"""Resolve Home Assistant media inputs for Matrix uploads."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from aiohttp import ClientResponse
from PIL import Image as PILImage

from homeassistant.components import camera, image, media_source
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import get_url

from .const import HTTP_TIMEOUT_SECONDS, MAX_MEDIA_BYTES, MEDIA_TYPES
from .content import (
    MediaType,
    infer_media_type,
    validate_media_item_shape,
    validate_media_size,
)

_HLS_MIME_TYPES = {
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
}


@dataclass(slots=True)
class ResolvedMedia:
    """Normalized media ready for a Matrix upload."""

    data: bytes
    filename: str
    content_type: str
    media_type: MediaType
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None

    @property
    def size(self) -> int:
        return len(self.data)

    def image_info(self) -> dict[str, Any]:
        """Return Matrix ThumbnailInfo-compatible metadata."""
        info: dict[str, Any] = {"mimetype": self.content_type, "size": self.size}
        if self.width is not None:
            info["w"] = self.width
        if self.height is not None:
            info["h"] = self.height
        return info


def _clean_content_type(value: str | None, filename: str) -> str:
    if value:
        value = value.split(";", 1)[0].strip().lower()
        if value and value != "application/octet-stream":
            return value
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _extension_for_mime(content_type: str) -> str:
    overrides = {
        "image/jpeg": ".jpg",
        "video/mp4": ".mp4",
        "audio/ogg": ".ogg",
    }
    return overrides.get(content_type) or mimetypes.guess_extension(content_type) or ""


def _image_dimensions(data: bytes) -> tuple[int, int]:
    with PILImage.open(BytesIO(data)) as img:
        return img.size


def _frigate_recording_proxy_url(url: str) -> str | None:
    """Map a Frigate timestamp VOD playlist to its HA MP4 recording proxy."""
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 9 or parts[:2] != ["api", "frigate"]:
        return None

    if parts[2] == "vod":
        prefix = parts[:2]
        vod = parts[2:]
    elif len(parts) >= 10 and parts[3] == "vod":
        prefix = parts[:3]
        vod = parts[3:]
    else:
        return None

    if (
        len(vod) != 7
        or vod[0] != "vod"
        or vod[2] != "start"
        or vod[4] != "end"
        or vod[6].lower() != "index.m3u8"
    ):
        return None

    camera_name, start, end = vod[1], vod[3], vod[5]
    if not camera_name or not start or not end:
        return None
    try:
        float(start)
        float(end)
    except ValueError:
        return None

    path = "/" + "/".join(
        [*prefix, "recording", camera_name, "start", start, "end", end]
    )
    return parsed._replace(path=path, query="", fragment="").geturl()


class MediaResolver:
    """Resolve the source forms supported by matrix_extended.send."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def async_resolve(
        self,
        item: dict[str, Any],
        *,
        force_type: MediaType | None = None,
    ) -> ResolvedMedia:
        """Resolve a service media object into bytes and metadata."""
        try:
            item = validate_media_item_shape(item)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

        if "entity_id" in item:
            resolved = await self._async_from_entity(item["entity_id"])
        elif "path" in item:
            resolved = await self._async_from_path(item["path"], trusted=False)
        elif "url" in item:
            resolved = await self._async_from_url(item["url"])
        else:
            resolved = await self._async_from_media_source(item["media_source"])

        try:
            validate_media_size(resolved.size, MAX_MEDIA_BYTES)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

        if filename := item.get("filename"):
            resolved.filename = filename
            resolved.content_type = _clean_content_type(resolved.content_type, filename)

        requested_type = item.get("type", "auto")
        if requested_type not in MEDIA_TYPES:
            raise HomeAssistantError(f"Unsupported media type: {requested_type}")
        if force_type is not None:
            resolved.media_type = force_type
        elif requested_type != "auto":
            resolved.media_type = requested_type
        else:
            resolved.media_type = infer_media_type(resolved.content_type)

        if item.get("width") is not None:
            resolved.width = item["width"]
        if item.get("height") is not None:
            resolved.height = item["height"]
        if item.get("duration_ms") is not None:
            resolved.duration_ms = item["duration_ms"]

        if resolved.media_type == "image" and (
            resolved.width is None or resolved.height is None
        ):
            try:
                resolved.width, resolved.height = await self.hass.async_add_executor_job(
                    _image_dimensions, resolved.data
                )
            except Exception as err:
                raise HomeAssistantError(
                    f"Unable to read image dimensions for {resolved.filename}: {err}"
                ) from err

        return resolved

    async def _async_from_entity(self, entity_id: str) -> ResolvedMedia:
        domain, _, object_id = entity_id.partition(".")
        if not object_id or domain not in {"camera", "image"}:
            raise HomeAssistantError(
                "entity_id media source must be a camera.* or image.* entity"
            )
        try:
            if domain == "camera":
                result = await camera.async_get_image(self.hass, entity_id)
            else:
                result = await image.async_get_image(self.hass, entity_id)
        except Exception as err:
            raise HomeAssistantError(f"Unable to fetch {entity_id}: {err}") from err
        content_type = _clean_content_type(result.content_type, object_id)
        filename = f"{object_id}{_extension_for_mime(content_type)}"
        return ResolvedMedia(
            data=result.content,
            filename=filename,
            content_type=content_type,
            media_type="image",
        )

    async def _async_from_path(self, path: str, *, trusted: bool) -> ResolvedMedia:
        if not trusted:
            allowed = await self.hass.async_add_executor_job(
                self.hass.config.is_allowed_path, path
            )
            if not allowed:
                raise HomeAssistantError(f"Path is not allowed by Home Assistant: {path}")
        file_path = Path(path)
        try:
            stat = await self.hass.async_add_executor_job(file_path.stat)
            if stat.st_size > MAX_MEDIA_BYTES:
                raise HomeAssistantError(
                    f"Attachment is too large ({stat.st_size} bytes); limit is {MAX_MEDIA_BYTES}"
                )
            data = await self.hass.async_add_executor_job(file_path.read_bytes)
        except HomeAssistantError:
            raise
        except OSError as err:
            raise HomeAssistantError(f"Unable to read {path}: {err}") from err
        filename = file_path.name or "attachment"
        content_type = _clean_content_type(None, filename)
        return ResolvedMedia(
            data=data,
            filename=filename,
            content_type=content_type,
            media_type=infer_media_type(content_type),
        )

    async def _async_from_url(self, url: str) -> ResolvedMedia:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise HomeAssistantError("URL media source must use http:// or https://")
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(url, timeout=HTTP_TIMEOUT_SECONDS) as response:
                response.raise_for_status()
                data = await self._async_read_limited(response)
                filename = unquote(Path(parsed.path).name) or "attachment"
                content_type = _clean_content_type(
                    response.headers.get("Content-Type"), filename
                )
        except HomeAssistantError:
            raise
        except Exception as err:
            raise HomeAssistantError(f"Unable to download {url}: {err}") from err
        return ResolvedMedia(
            data=data,
            filename=filename,
            content_type=content_type,
            media_type=infer_media_type(content_type),
        )

    async def _async_read_limited(self, response: ClientResponse) -> bytes:
        length = response.headers.get("Content-Length")
        if length is not None and int(length) > MAX_MEDIA_BYTES:
            raise HomeAssistantError(
                f"Attachment is too large ({length} bytes); limit is {MAX_MEDIA_BYTES}"
            )
        data = bytearray()
        async for chunk in response.content.iter_chunked(64 * 1024):
            data.extend(chunk)
            if len(data) > MAX_MEDIA_BYTES:
                raise HomeAssistantError(
                    f"Attachment exceeded the {MAX_MEDIA_BYTES}-byte limit while downloading"
                )
        return bytes(data)

    def _process_media_source_url(self, url: str) -> str:
        """Sign Home Assistant-owned media URLs before downloading them."""
        try:
            from homeassistant.components.media_player.browse_media import (  # noqa: PLC0415
                async_process_play_media_url,
            )
        except ImportError:
            # Compatibility with older Home Assistant releases; current HA always
            # provides the helper and signs protected internal URLs here.
            if url.startswith("/"):
                return f"{get_url(self.hass, prefer_external=False).rstrip('/')}{url}"
            return url
        return async_process_play_media_url(self.hass, url)

    async def _async_from_media_source(self, media_id: str) -> ResolvedMedia:
        try:
            playable = await media_source.async_resolve_media(
                self.hass, media_id, target_media_player=None
            )
        except Exception as err:
            raise HomeAssistantError(
                f"Unable to resolve media source {media_id}: {err}"
            ) from err
        if playable.path is not None:
            resolved = await self._async_from_path(str(playable.path), trusted=True)
            resolved.content_type = _clean_content_type(
                playable.mime_type, resolved.filename
            )
            resolved.media_type = infer_media_type(resolved.content_type)
            return resolved

        url = playable.url
        playable_mime = _clean_content_type(playable.mime_type, urlparse(url).path)
        frigate_recording_url = None
        if playable_mime in _HLS_MIME_TYPES:
            frigate_recording_url = _frigate_recording_proxy_url(url)

        if frigate_recording_url is not None:
            resolved = await self._async_from_url(
                self._process_media_source_url(frigate_recording_url)
            )
            resolved.content_type = "video/mp4"
            if not resolved.filename.lower().endswith(".mp4"):
                resolved.filename = f"{resolved.filename}.mp4"
            resolved.media_type = "video"
            return resolved

        resolved = await self._async_from_url(self._process_media_source_url(url))
        resolved.content_type = _clean_content_type(playable.mime_type, resolved.filename)
        resolved.media_type = infer_media_type(resolved.content_type)
        return resolved
