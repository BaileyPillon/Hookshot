"""Experimental checkpoint envelope and restore selection; no game capture or restore implementation.

SPDX-License-Identifier: GPL-3.0-or-later
The portable provider must validate and apply its own payload at a proven runtime safe point.
This module never applies payloads, deserializes executable objects, or extracts ZIP paths.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile

SCHEMA = 1
MAX_MANIFEST = 16 * 1024
MAX_PORTABLE = 64 * 1024
# A bounded first-format prototype, NOT enough for Hookshot's full guest address space.
MAX_EXACT = 64 * 1024 * 1024


class CheckpointError(ValueError):
    pass


def _hex(value, digits):
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{%d}" % digits, value) is not None


@dataclass(frozen=True)
class Identity:
    program_id: str
    game_build_id: str
    runtime_build: str
    runtime_sha256: str
    platform: str
    state_abi: int
    mod_set_sha256: str
    config_sha256: str

    def validate(self):
        # nso.py preserves up to 32 bytes and strips trailing zero bytes, not a fixed SHA-1.
        if not _hex(self.program_id, 16) or not isinstance(self.game_build_id, str) \
                or re.fullmatch(r"(?:[0-9a-f]{2}){1,32}", self.game_build_id) is None:
            raise CheckpointError("invalid game identity")
        if not isinstance(self.runtime_build, str) or not 1 <= len(self.runtime_build) <= 160:
            raise CheckpointError("invalid runtime identity")
        if not _hex(self.runtime_sha256, 64) or not isinstance(self.platform, str) \
                or re.fullmatch(r"[a-z0-9_-]{1,64}", self.platform) is None:
            raise CheckpointError("missing runtime/platform fingerprints")
        if type(self.state_abi) is not int or self.state_abi < 1:
            raise CheckpointError("invalid snapshot ABI")
        if not _hex(self.mod_set_sha256, 64) or not _hex(self.config_sha256, 64):
            raise CheckpointError("missing mod/configuration fingerprints")


@dataclass(frozen=True)
class Checkpoint:
    identity: Identity
    provider: str
    provider_schema: int
    portable: dict
    exact: bytes | None


@dataclass(frozen=True)
class RestorePlan:
    mode: str
    reason: str


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CheckpointError("duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(value):
    raise CheckpointError("non-finite JSON number: " + value)


def _json(data):
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_nonfinite)
        _encode(value)  # also rejects exponent overflow (1e999), and invalid Unicode escapes
        return value
    except (ValueError, UnicodeError, RecursionError) as error:
        raise CheckpointError("invalid checkpoint JSON") from error


def _encode(data):
    try:
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise CheckpointError("payload is not finite JSON") from error


def _provider(provider, schema):
    if not isinstance(provider, str) or re.fullmatch(r"[a-z][a-z0-9_.-]{0,95}", provider) is None:
        raise CheckpointError("invalid portable provider")
    if type(schema) is not int or schema < 1:
        raise CheckpointError("invalid portable provider schema")


def write_checkpoint(path, checkpoint):
    """Write to a sibling temporary file, then atomically replace the destination.

    Provider payloads are plain JSON; exact bytes are an opaque, bounded prototype.
    A failure before os.replace leaves any existing checkpoint intact.
    """
    checkpoint.identity.validate()
    _provider(checkpoint.provider, checkpoint.provider_schema)
    if not isinstance(checkpoint.portable, dict):
        raise CheckpointError("portable payload must be an object")
    portable = _encode(checkpoint.portable)
    if len(portable) > MAX_PORTABLE:
        raise CheckpointError("portable payload is too large")
    payloads = {"portable.json": portable}
    if checkpoint.exact is not None:
        if not isinstance(checkpoint.exact, bytes) or not 0 < len(checkpoint.exact) <= MAX_EXACT:
            raise CheckpointError("exact payload is empty or too large")
        payloads["exact.bin"] = checkpoint.exact
    manifest = {"schema": SCHEMA, "identity": asdict(checkpoint.identity),
                "provider": checkpoint.provider, "provider_schema": checkpoint.provider_schema,
                "payloads": {name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                             for name, data in payloads.items()}}
    encoded_manifest = _encode(manifest)
    if len(encoded_manifest) > MAX_MANIFEST:
        raise CheckpointError("manifest is too large")
    destination = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=".hookshot-checkpoint-", dir=destination.parent)
    try:
        with os.fdopen(fd, "w+b") as stream:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("manifest.json", encoded_manifest)
                for name, data in payloads.items():
                    archive.writestr(name, data)
            stream.flush()
            os.fsync(stream.fileno())
        # Check the completed file before it can replace the previous checkpoint.
        read_checkpoint(temporary)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_checkpoint(path):
    limits = {"manifest.json": MAX_MANIFEST, "portable.json": MAX_PORTABLE, "exact.bin": MAX_EXACT}
    try:
        if Path(path).stat().st_size > MAX_EXACT + MAX_PORTABLE + MAX_MANIFEST + 4096:
            raise CheckpointError("archive exceeds its bound")
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(names) != len(set(names)) or set(names) not in (
                    {"manifest.json", "portable.json"}, {"manifest.json", "portable.json", "exact.bin"}):
                raise CheckpointError("unexpected or duplicate archive entries")
            for entry in entries:
                if entry.compress_type != zipfile.ZIP_STORED or entry.flag_bits & 1:
                    raise CheckpointError("compressed/encrypted payloads are not supported by schema 1")
                if entry.file_size > limits[entry.filename] or entry.compress_size != entry.file_size:
                    raise CheckpointError("payload size exceeds its bound")
            manifest = _json(archive.read("manifest.json"))
            if not isinstance(manifest, dict) or set(manifest) != {
                    "schema", "identity", "provider", "provider_schema", "payloads"}:
                raise CheckpointError("invalid manifest")
            if type(manifest["schema"]) is not int or manifest["schema"] != SCHEMA:
                raise CheckpointError("unsupported checkpoint schema")
            try:
                identity = Identity(**manifest["identity"])
            except (TypeError, KeyError) as error:
                raise CheckpointError("invalid checkpoint identity") from error
            identity.validate()
            _provider(manifest["provider"], manifest["provider_schema"])
            hashes = manifest["payloads"]
            if not isinstance(hashes, dict) or set(hashes) != set(names) - {"manifest.json"}:
                raise CheckpointError("payload manifest mismatch")
            payloads = {}
            for name, expected in hashes.items():
                if not isinstance(expected, dict) or set(expected) != {"size", "sha256"}:
                    raise CheckpointError("invalid payload checksum record")
                data = archive.read(name)
                if type(expected["size"]) is not int or expected["size"] != len(data) or not _hex(expected["sha256"], 64) \
                        or hashlib.sha256(data).hexdigest() != expected["sha256"]:
                    raise CheckpointError("payload checksum mismatch")
                payloads[name] = data
            portable = _json(payloads["portable.json"])
            if not isinstance(portable, dict) or ("exact.bin" in payloads and not payloads["exact.bin"]):
                raise CheckpointError("invalid payload")
            return Checkpoint(identity, manifest["provider"], manifest["provider_schema"],
                              portable, payloads.get("exact.bin"))
    except (zipfile.BadZipFile, EOFError, OSError, RuntimeError, OverflowError) as error:
        raise CheckpointError("cannot read checkpoint") from error


def choose_restore(checkpoint, current, *, exact_supported=False, portable_providers=None):
    """Legacy schema 1 is inspection-only; use hookshot_statefile for restore planning.

    Schema 1 cannot bind a state to its native save slot or detect rebased code,
    changed host resources or an incompatible live scheduler. A boolean exact
    capability must never bypass that missing evidence.
    """
    checkpoint.identity.validate()
    current.validate()
    _provider(checkpoint.provider, checkpoint.provider_schema)
    return RestorePlan("reject", "legacy schema 1 lacks native save binding and exact runtime evidence; inspection only")
