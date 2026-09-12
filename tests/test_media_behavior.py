from __future__ import annotations

from io import BytesIO
import importlib.util
from pathlib import Path
import sys
import types

import pytest
from PIL import Image as PILImage

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"


class FakeHomeAssistantError(Exception):
    pass


class FakeConfig:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.calls = []

    def is_allowed_path(self, path):
        self.calls.append(path)
        return self.allowed


class FakeHass:
    def __init__(self, allowed=True):
        self.config = FakeConfig(allowed)

    async def async_add_executor_job(self, func, *args):
        return func(*args)


class FakeContent:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    async def iter_chunked(self, size):
        for chunk in self.chunks:
            yield chunk


class FakeResponse:
    def __init__(self, *, chunks=(b"data",), headers=None, error=None):
        self.headers = dict(headers or {})
        self.content = FakeContent(chunks)
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        if self.error:
            raise self.error


class FakeSession:
    def __init__(self, response=None):
        self.response = response or FakeResponse()
        self.calls = []

    def get(self, url, *, timeout):
        self.calls.append((url, timeout))
        return self.response


def png_bytes(width=2, height=3):
    bio = BytesIO()
    PILImage.new("RGB", (width, height)).save(bio, format="PNG")
    return bio.getvalue()


def load_media():
    pkg_name = "matrix_extended_media_testpkg"
    package = types.ModuleType(pkg_name)
    package.__path__ = [str(COMP)]
    sys.modules[pkg_name] = package

    state = types.SimpleNamespace(
        camera_result=types.SimpleNamespace(content=png_bytes(), content_type="image/png"),
        image_result=types.SimpleNamespace(content=png_bytes(), content_type="image/png"),
        camera_error=None,
        image_error=None,
        playable=None,
        media_error=None,
        session=FakeSession(),
        get_url_calls=[],
    )

    aiohttp = types.ModuleType("aiohttp")
    aiohttp.ClientResponse = object
    sys.modules["aiohttp"] = aiohttp

    ha = types.ModuleType("homeassistant")
    components = types.ModuleType("homeassistant.components")
    camera = types.ModuleType("homeassistant.components.camera")
    image = types.ModuleType("homeassistant.components.image")
    media_source = types.ModuleType("homeassistant.components.media_source")

    async def camera_get(hass, entity_id):
        if state.camera_error:
            raise state.camera_error
        return state.camera_result

    async def image_get(hass, entity_id):
        if state.image_error:
            raise state.image_error
        return state.image_result

    async def resolve_media(hass, media_id, target_media_player=None):
        if state.media_error:
            raise state.media_error
        return state.playable

    camera.async_get_image = camera_get
    image.async_get_image = image_get
    media_source.async_resolve_media = resolve_media
    components.camera = camera
    components.image = image
    components.media_source = media_source

    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    exceptions = types.ModuleType("homeassistant.exceptions")
    exceptions.HomeAssistantError = FakeHomeAssistantError
    helpers = types.ModuleType("homeassistant.helpers")
    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
    network = types.ModuleType("homeassistant.helpers.network")
    aiohttp_client.async_get_clientsession = lambda hass: state.session
    def fake_get_url(hass, prefer_external=False):
        state.get_url_calls.append(prefer_external)
        return "http://ha.local/"
    network.get_url = fake_get_url

    for name, mod in {
        "homeassistant": ha,
        "homeassistant.components": components,
        "homeassistant.components.camera": camera,
        "homeassistant.components.image": image,
        "homeassistant.components.media_source": media_source,
        "homeassistant.core": core,
        "homeassistant.exceptions": exceptions,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.aiohttp_client": aiohttp_client,
        "homeassistant.helpers.network": network,
    }.items():
        sys.modules[name] = mod

    def load_local(name):
        spec = importlib.util.spec_from_file_location(
            f"{pkg_name}.{name}", COMP / f"{name}.py"
        )
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod

    load_local("const")
    load_local("content")
    spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.media", COMP / "media.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod, state


def test_resolved_media_size_image_info_and_slots() -> None:
    mod, _ = load_media()
    resolved = mod.ResolvedMedia(
        data=b"abc",
        filename="x.jpg",
        content_type="image/jpeg",
        media_type="image",
        width=10,
        height=20,
    )
    assert resolved.size == 3
    assert resolved.image_info() == {
        "mimetype": "image/jpeg",
        "size": 3,
        "w": 10,
        "h": 20,
    }
    assert not hasattr(resolved, "__dict__")


def test_clean_content_type_and_extension_rules() -> None:
    mod, _ = load_media()
    assert mod._clean_content_type("IMAGE/JPEG; charset=UTF-8", "x.bin") == "image/jpeg"
    assert mod._clean_content_type("application/octet-stream", "photo.jpg") == "image/jpeg"
    assert mod._clean_content_type(None, "unknown.no_such_ext") == "application/octet-stream"
    assert mod._extension_for_mime("image/jpeg") == ".jpg"
    assert mod._extension_for_mime("video/mp4") == ".mp4"
    assert mod._extension_for_mime("audio/ogg") == ".ogg"


@pytest.mark.asyncio
async def test_entity_sources_camera_and_image_and_invalid_entity() -> None:
    mod, state = load_media()
    resolver = mod.MediaResolver(FakeHass())
    cam = await resolver._async_from_entity("camera.front")
    assert cam.filename == "front.png"
    assert cam.content_type == "image/png"
    assert cam.media_type == "image"
    img = await resolver._async_from_entity("image.poster")
    assert img.filename == "poster.png"
    with pytest.raises(FakeHomeAssistantError, match="camera.*image"):
        await resolver._async_from_entity("sensor.bad")
    state.camera_error = RuntimeError("camera down")
    with pytest.raises(FakeHomeAssistantError, match="camera down"):
        await resolver._async_from_entity("camera.front")


@pytest.mark.asyncio
async def test_async_resolve_infers_image_dimensions_and_honors_overrides(tmp_path) -> None:
    mod, _ = load_media()
    path = tmp_path / "picture.png"
    path.write_bytes(png_bytes(4, 5))
    hass = FakeHass(allowed=True)
    resolver = mod.MediaResolver(hass)
    resolved = await resolver.async_resolve({"path": str(path)})
    assert resolved.media_type == "image"
    assert (resolved.width, resolved.height) == (4, 5)
    assert hass.config.calls == [str(path)]

    forced = await resolver.async_resolve(
        {
            "path": str(path),
            "filename": "renamed.bin",
            "type": "file",
            "width": 7,
            "height": 8,
            "duration_ms": 9,
        },
        force_type="video",
    )
    assert forced.filename == "renamed.bin"
    assert forced.media_type == "video"
    assert (forced.width, forced.height, forced.duration_ms) == (7, 8, 9)
    with pytest.raises(FakeHomeAssistantError, match="Unsupported media type"):
        await resolver.async_resolve({"path": str(path), "type": "bogus"})


@pytest.mark.asyncio
async def test_path_security_and_exact_size_boundary(tmp_path) -> None:
    mod, _ = load_media()
    path = tmp_path / "x.bin"
    path.write_bytes(b"abc")
    denied = mod.MediaResolver(FakeHass(allowed=False))
    with pytest.raises(FakeHomeAssistantError, match="not allowed"):
        await denied._async_from_path(str(path), trusted=False)

    mod.MAX_MEDIA_BYTES = 3
    allowed = mod.MediaResolver(FakeHass(allowed=True))
    exact = await allowed._async_from_path(str(path), trusted=False)
    assert exact.data == b"abc"
    path.write_bytes(b"abcd")
    with pytest.raises(FakeHomeAssistantError, match="too large"):
        await allowed._async_from_path(str(path), trusted=False)


@pytest.mark.asyncio
async def test_url_source_validates_scheme_and_parses_headers() -> None:
    mod, state = load_media()
    state.session = FakeSession(
        FakeResponse(
            chunks=(b"ab", b"cd"),
            headers={"Content-Type": "VIDEO/MP4; charset=x", "Content-Length": "4"},
        )
    )
    resolver = mod.MediaResolver(FakeHass())
    with pytest.raises(FakeHomeAssistantError, match="http"):
        await resolver._async_from_url("ftp://example/file.mp4")
    resolved = await resolver._async_from_url("https://example/a%20b.mp4")
    assert resolved.data == b"abcd"
    assert resolved.filename == "a b.mp4"
    assert resolved.content_type == "video/mp4"
    assert resolved.media_type == "video"
    assert state.session.calls[0][0] == "https://example/a%20b.mp4"


@pytest.mark.asyncio
async def test_stream_limits_accept_exact_boundary_and_reject_excess() -> None:
    mod, _ = load_media()
    mod.MAX_MEDIA_BYTES = 3
    resolver = mod.MediaResolver(FakeHass())
    exact = FakeResponse(chunks=(b"a", b"bc"), headers={"Content-Length": "3"})
    assert await resolver._async_read_limited(exact) == b"abc"
    header_too_big = FakeResponse(chunks=(b"abc",), headers={"Content-Length": "4"})
    with pytest.raises(FakeHomeAssistantError, match="too large"):
        await resolver._async_read_limited(header_too_big)
    streamed_too_big = FakeResponse(chunks=(b"ab", b"cd"), headers={})
    with pytest.raises(FakeHomeAssistantError, match="exceeded"):
        await resolver._async_read_limited(streamed_too_big)


@pytest.mark.asyncio
async def test_media_source_path_is_trusted_and_mime_is_overridden(tmp_path) -> None:
    mod, state = load_media()
    path = tmp_path / "clip.bin"
    path.write_bytes(b"abc")
    state.playable = types.SimpleNamespace(
        path=path,
        url="",
        mime_type="video/mp4",
    )
    hass = FakeHass(allowed=False)
    resolver = mod.MediaResolver(hass)
    resolved = await resolver._async_from_media_source("media-source://local/clip")
    assert resolved.data == b"abc"
    assert resolved.content_type == "video/mp4"
    assert resolved.media_type == "video"
    assert hass.config.calls == []


@pytest.mark.asyncio
async def test_media_source_relative_url_uses_internal_ha_url() -> None:
    mod, state = load_media()
    state.playable = types.SimpleNamespace(
        path=None,
        url="/media/file.ogg",
        mime_type="audio/ogg",
    )
    state.session = FakeSession(FakeResponse(chunks=(b"ogg",), headers={}))
    resolver = mod.MediaResolver(FakeHass())
    resolved = await resolver._async_from_media_source("media-source://remote/file")
    assert state.session.calls[0][0] == "http://ha.local/media/file.ogg"
    assert state.get_url_calls == [False]
    assert resolved.content_type == "audio/ogg"
    assert resolved.media_type == "audio"


@pytest.mark.asyncio
async def test_media_source_resolution_error_is_wrapped() -> None:
    mod, state = load_media()
    state.media_error = RuntimeError("resolver down")
    resolver = mod.MediaResolver(FakeHass())
    with pytest.raises(FakeHomeAssistantError, match="resolver down"):
        await resolver._async_from_media_source("media-source://bad")


@pytest.mark.asyncio
async def test_public_resolve_url_branch_is_selected() -> None:
    mod, state = load_media()
    state.session = FakeSession(FakeResponse(chunks=(b"abc",), headers={"Content-Type": "application/pdf"}))
    resolver = mod.MediaResolver(FakeHass())
    resolved = await resolver.async_resolve({"url": "https://example/file.pdf"})
    assert resolved.filename == "file.pdf"
    assert resolved.media_type == "file"
    assert state.session.calls[0][0] == "https://example/file.pdf"


@pytest.mark.asyncio
async def test_image_dimension_probe_runs_when_only_height_is_missing(tmp_path) -> None:
    mod, _ = load_media()
    path = tmp_path / "picture.png"
    path.write_bytes(png_bytes(4, 5))
    resolver = mod.MediaResolver(FakeHass())
    resolved = await resolver.async_resolve({"path": str(path), "width": 99})
    assert (resolved.width, resolved.height) == (4, 5)


@pytest.mark.asyncio
async def test_image_dimension_probe_runs_when_only_width_is_missing(tmp_path) -> None:
    mod, _ = load_media()
    path = tmp_path / "picture.png"
    path.write_bytes(png_bytes(4, 5))
    resolver = mod.MediaResolver(FakeHass())
    resolved = await resolver.async_resolve({"path": str(path), "height": 99})
    assert (resolved.width, resolved.height) == (4, 5)


@pytest.mark.asyncio
async def test_non_image_with_missing_dimensions_does_not_probe_image(tmp_path) -> None:
    mod, _ = load_media()
    path = tmp_path / "file.bin"
    path.write_bytes(b"not an image")
    resolver = mod.MediaResolver(FakeHass())
    resolved = await resolver.async_resolve({"path": str(path), "type": "file"})
    assert resolved.media_type == "file"
    assert resolved.width is None
    assert resolved.height is None
