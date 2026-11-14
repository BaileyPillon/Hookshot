"""Sunshine-inspired two-path checkpoint storage. No game-memory access or restore backend.

SPDX-License-Identifier: GPL-3.0-or-later
Independent implementation; design reference: docs/sunshine-checkpoints.md.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path
import re
import struct
import tempfile
import threading

from hookshot_checkpoint import CheckpointError, Identity, RestorePlan, _encode, _hex, _json, _provider

MAGIC = b"HOSSTATE"
VERSION = 2
HEADER = struct.Struct("<8sII")
CHUNK = struct.Struct("<4sIQ32s")  # tag, flags, byte count, SHA-256(index, tag, flags, raw bytes)
REQUIRED = 1
BLOCK = 4 * 1024 * 1024
MAX_CHUNKS = 4098  # META, PORT, and at most 16 GiB of exact data in 4 MiB blocks
MAX_EXACT = 16 * 1024**3
MAX_SMALL = 64 * 1024
MAX_PORTABLE = BLOCK  # complete persistent OoT progress may exceed the observation prototype's 64 KiB


class CommittedStateError(CheckpointError):
    """Atomic replacement succeeded, but crash durability could not be confirmed."""
    committed = True


def _checksum(index, tag, flags, data):
    digest = hashlib.sha256(struct.pack("<I4sI", index, tag, flags))
    digest.update(data)
    return digest.digest()


@dataclass(frozen=True)
class SaveBinding:
    """Opaque native identifiers, never a filename supplied by a state author."""
    profile: str
    save_data: str
    slot: str

    def validate(self):
        for value in (self.profile, self.save_data, self.slot):
            if not isinstance(value, str) or re.fullmatch(r"[a-zA-Z0-9_.-]{1,96}", value) is None \
                    or value in (".", ".."):
                raise CheckpointError("invalid or unbound native save identity")

    def digest(self):
        """Canonical native-ticket binding: domain prefix then three length-prefixed UTF-8 IDs."""
        self.validate()
        digest = hashlib.sha256(b"HOS-SAVE-BINDING-v1\0")
        for value in (self.profile, self.save_data, self.slot):
            data = value.encode("utf-8")
            digest.update(struct.pack("<I", len(data)))
            digest.update(data)
        return digest.digest()


@dataclass(frozen=True)
class ExactContext:
    """Runtime evidence beyond a matching executable, obtained from the native backend."""
    code_anchor: int
    guest_base: int
    layout_sha256: str
    threads_sha256: str
    resources_abi_sha256: str

    def validate(self):
        if any(type(value) is not int or not 0 < value < 2**64 for value in (self.code_anchor, self.guest_base)):
            raise CheckpointError("missing native code/guest mapping anchors")
        if any(not _hex(value, 64) for value in (self.layout_sha256, self.threads_sha256, self.resources_abi_sha256)):
            raise CheckpointError("missing exact-state runtime signatures")


@dataclass(frozen=True)
class StateInfo:
    identity: Identity
    provider: str
    provider_schema: int
    binding: SaveBinding
    portable: dict
    exact_context: ExactContext | None
    exact_bytes: int
    exact_blocks: int
    exact_error: str | None
    optional_tags: tuple[str, ...]


def _metadata(identity, provider, schema, binding, context):
    identity.validate()
    _provider(provider, schema)
    binding.validate()
    if context is not None:
        context.validate()
    data = _encode({"schema": VERSION, "identity": asdict(identity), "provider": provider,
                    "provider_schema": schema, "binding": asdict(binding),
                    "exact_context": asdict(context) if context is not None else None})
    if len(data) > MAX_SMALL:
        raise CheckpointError("metadata exceeds its bound")
    return data


def _decode_metadata(data):
    value = _json(data)
    if not isinstance(value, dict) or set(value) != {
            "schema", "identity", "provider", "provider_schema", "binding", "exact_context"} \
            or type(value["schema"]) is not int or value["schema"] != VERSION:
        raise CheckpointError("invalid checkpoint metadata")
    try:
        identity = Identity(**value["identity"])
        binding = SaveBinding(**value["binding"])
        context = ExactContext(**value["exact_context"]) if value["exact_context"] is not None else None
    except TypeError as error:
        raise CheckpointError("invalid checkpoint identities") from error
    _metadata(identity, value["provider"], value["provider_schema"], binding, context)
    return identity, value["provider"], value["provider_schema"], binding, context


def _read(stream, count):
    data = stream.read(count)
    if len(data) != count:
        raise CheckpointError("truncated checkpoint")
    return data


def _scan(stream, exact_output=None):
    magic, version, count = HEADER.unpack(_read(stream, HEADER.size))
    if magic != MAGIC or version != VERSION or not 2 <= count <= MAX_CHUNKS:
        raise CheckpointError("unsupported checkpoint header or chunk count")
    metadata = portable = None
    exact_bytes = exact_blocks = 0
    exact_error = None
    optional = []
    for index in range(count):
        tag, flags, size, checksum = CHUNK.unpack(_read(stream, CHUNK.size))
        if flags & ~REQUIRED or not all(65 <= byte <= 90 for byte in tag):
            raise CheckpointError("invalid chunk tag or flags")
        if (index == 0 and tag != b"META") or (index == 1 and tag != b"PORT"):
            raise CheckpointError("metadata and portable chunks must precede exact data")
        limit = MAX_SMALL if tag == b"META" else MAX_PORTABLE if tag == b"PORT" else BLOCK
        if size > limit:
            raise CheckpointError("chunk exceeds its bound")
        if tag in (b"META", b"PORT") and (index > 1 or flags != REQUIRED):
            raise CheckpointError("duplicate or optional metadata/portable chunk")
        if tag not in (b"META", b"PORT", b"EXAC") and flags & REQUIRED:
            raise CheckpointError("unknown required chunk")
        if tag == b"EXAC" and (flags or not size):
            raise CheckpointError("invalid exact block")
        data = _read(stream, size)
        valid = _checksum(index, tag, flags, data) == checksum
        if tag == b"EXAC":
            exact_blocks += 1
            exact_bytes += size
            if exact_bytes > MAX_EXACT:
                raise CheckpointError("exact payload exceeds its bound")
            if not valid:
                exact_error = "an exact block failed its integrity check"
            if exact_output is not None:
                exact_output.write(data)  # staging file only, never a live guest pointer
        elif not valid:
            raise CheckpointError("checkpoint chunk failed its integrity check")
        elif tag == b"META":
            metadata = _decode_metadata(data)
        elif tag == b"PORT":
            portable = _json(data)
            if not isinstance(portable, dict):
                raise CheckpointError("portable payload must be an object")
        else:
            optional.append(tag.decode("ascii"))
    if stream.read(1):
        raise CheckpointError("trailing checkpoint data")
    if metadata is None or portable is None or (exact_blocks and metadata[4] is None):
        raise CheckpointError("missing checkpoint identity or exact context")
    return StateInfo(*metadata[:4], portable, metadata[4], exact_bytes, exact_blocks, exact_error, tuple(optional))


def read_state(path):
    """Validate the whole file with at most one 4 MiB block in memory.

    A damaged EXAC block disables exact restore, preserving a verified PORT fallback.
    Framing, metadata and portable corruption reject the entire state.
    """
    try:
        with Path(path).open("rb") as stream:
            return _scan(stream)
    except (OSError, struct.error) as error:
        raise CheckpointError("cannot read checkpoint") from error


def _chunk(stream, index, tag, flags, data):
    stream.write(CHUNK.pack(tag, flags, len(data), _checksum(index, tag, flags, data)))
    stream.write(data)


def _parent_sync(path):
    # Atomic visibility is portable; crash durability also needs the directory flushed on POSIX.
    if os.name == "posix":
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _commit(temporary, destination):
    os.replace(temporary, destination)
    try:
        _parent_sync(destination.parent)
    except OSError as error:
        raise CommittedStateError("checkpoint committed; directory durability could not be confirmed") from error


def write_state(path, *, identity, provider, provider_schema, binding, portable, exact_context=None,
                exact_blocks=()):
    """Write immutable captured values on a worker, with streamed exact blocks.

    Iteration must read an owned snapshot, not a running game's heap. The caller
    owns the iterable until this function completes. Existing states survive any
    failure before atomic replacement; no original save files are touched.
    """
    metadata = _metadata(identity, provider, provider_schema, binding, exact_context)
    if not isinstance(portable, dict):
        raise CheckpointError("portable payload must be an object")
    portable_bytes = _encode(portable)
    if len(portable_bytes) > MAX_PORTABLE:
        raise CheckpointError("portable payload exceeds its bound")
    destination = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".hookshot-state-", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w+b") as stream:
            stream.write(HEADER.pack(MAGIC, VERSION, 0))
            _chunk(stream, 0, b"META", REQUIRED, metadata)
            _chunk(stream, 1, b"PORT", REQUIRED, portable_bytes)
            count, total = 2, 0
            for block in exact_blocks:
                if exact_context is None or type(block) is not bytes or not 0 < len(block) <= BLOCK:
                    raise CheckpointError("exact blocks require context and owned bytes within the block bound")
                count += 1
                total += len(block)
                if count > MAX_CHUNKS or total > MAX_EXACT:
                    raise CheckpointError("exact snapshot exceeds its bound")
                _chunk(stream, count - 1, b"EXAC", 0, block)
            stream.seek(0)
            stream.write(HEADER.pack(MAGIC, VERSION, count))
            stream.flush()
            os.fsync(stream.fileno())
            stream.seek(0)
            verified = _scan(stream)
            if verified.exact_error:
                raise CheckpointError(verified.exact_error)
        _commit(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def stage_exact(path, destination):
    """Stage verified bytes to a local file, atomically. This does not restore memory."""
    destination = Path(destination)
    if Path(path).resolve() == destination.resolve():
        raise CheckpointError("staging must not replace the checkpoint")
    descriptor, temporary = tempfile.mkstemp(prefix=".hookshot-exact-", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as output, Path(path).open("rb") as source:
            info = _scan(source, output)
            if not info.exact_blocks or info.exact_error:
                raise CheckpointError(info.exact_error or "checkpoint has no exact data")
            output.flush()
            os.fsync(output.fileno())
        _commit(temporary, destination)
        return info
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def choose_restore(info, current, *, binding, context=None, exact_supported=False, portable_providers=None):
    """Preflight only. The native coordinator revalidates identities at its boundary."""
    current.validate()
    binding.validate()
    saved = info.identity
    if (saved.program_id, saved.game_build_id) != (current.program_id, current.game_build_id):
        return RestorePlan("reject", "different game or game build; migration requires a separate provider")
    if saved.mod_set_sha256 != current.mod_set_sha256 or saved.config_sha256 != current.config_sha256:
        return RestorePlan("reject", "mod/configuration fingerprints differ")
    if info.binding != binding:
        return RestorePlan("reject", "checkpoint belongs to another profile, save data or slot")
    if info.provider == "hookshot.player-observation":
        return RestorePlan("reject", "an observation is not a restorable checkpoint")
    if context is not None:
        context.validate()
    if exact_supported is True and context is not None and info.exact_context == context \
            and info.exact_blocks and not info.exact_error and saved == current:
        return RestorePlan("exact", "matching build, mapping, memory, scheduler and resource signatures")
    schema = (portable_providers or {}).get(info.provider)
    if type(schema) is int and schema == info.provider_schema:
        return RestorePlan("portable", info.exact_error or "exact context/capability differs; reload scene and apply portable state")
    return RestorePlan("reject", "no compatible restore provider")


class StateWriter:
    """One background write at a time; the caller transfers an owned frozen capture.

    close() drains the job before releasing ownership. It belongs outside guest
    callbacks. No cancellation is promised once a write can commit its file.
    """
    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hookshot-state")
        self._future = None
        self._closed = False
        self._lock = threading.Lock()

    def submit(self, path, **capture):
        with self._lock:
            if self._closed or self._future is not None:
                return False
            # Snapshot small mutable values before ownership crosses to the worker.
            capture = dict(capture)
            portable = _encode(capture["portable"])
            if len(portable) > MAX_PORTABLE:
                raise CheckpointError("portable payload exceeds its bound")
            capture["portable"] = _json(portable)
            self._future = self._executor.submit(write_state, path, **capture)
            return True

    def poll(self):
        """None idle, 'writing', 'saved', or an exception from the completed job.

        Completion must be consumed before accepting another capture.
        """
        with self._lock:
            if self._future is None:
                return None
            if not self._future.done():
                return "writing"
            future, self._future = self._future, None
            error = future.exception()
            return error if error is not None else "saved"

    def close(self):
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=True)
