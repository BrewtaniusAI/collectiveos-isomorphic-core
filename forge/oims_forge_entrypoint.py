"""Verify the installed Forge controller before importing any project code."""

from __future__ import annotations

import ctypes
import hashlib
import importlib.util
import os
import stat
import struct
import sys
from pathlib import Path
from typing import NamedTuple

ATTESTATION_PATH = Path("/usr/local/share/oims-forge/source.attestation")
NVIDIA_RUNTIME_APPROVALS_PATH = Path("/usr/local/share/oims-forge/nvidia-runtime.approved")
MOUNTINFO_PATH = Path("/proc/self/mountinfo")
PROCESS_MAPS_PATH = Path("/proc/self/maps")
SANDBOX_OBSERVATION_PATHS = (
    Path("/proc/self/mountinfo"),
    Path("/proc/self/maps"),
    Path("/proc/self/status"),
    Path("/proc/self/cgroup"),
    Path("/proc/meminfo"),
    Path("/proc/mounts"),
    Path("/proc/net/route"),
    Path("/sys/class/net"),
    Path("/sys/fs/cgroup"),
)
OBSERVATION_ROOT_FILESYSTEMS = {
    Path("/proc"): frozenset({"proc"}),
    Path("/sys"): frozenset({"sysfs"}),
    Path("/sys/fs/cgroup"): frozenset({"cgroup2"}),
}
NATIVE_RUNTIME_ROOTS = (
    Path("/bin"),
    Path("/sbin"),
    Path("/lib"),
    Path("/lib64"),
    Path("/usr/bin"),
    Path("/usr/sbin"),
    Path("/usr/lib"),
    Path("/usr/lib64"),
)
DYNAMIC_LOADER_CONFIGURATION = (
    Path("/etc/ld.so.cache"),
    Path("/etc/ld.so.conf"),
    Path("/etc/ld.so.conf.d"),
    Path("/etc/ld.so.preload"),
)
NVIDIA_RUNTIME_ATTESTATION_ENV = "OIMS_FORGE_NVIDIA_RUNTIME_SHA256"
NVIDIA_SMI_PATH_ENV = "OIMS_FORGE_NVIDIA_SMI_PATH"
NVIDIA_RUNTIME_EXECUTABLES = frozenset(
    {
        "nvidia-smi",
        "nvidia-debugdump",
        "nvidia-persistenced",
        "nvidia-cuda-mps-control",
        "nvidia-cuda-mps-server",
    }
)
MAX_NVIDIA_RUNTIME_MOUNTS = 256
MAX_NVIDIA_RUNTIME_BYTES = 2 * 1024**3
MAX_ATTESTATION_BYTES = 256
MAX_NVIDIA_APPROVAL_BYTES = 128 * 1024
MAX_PROC_METADATA_BYTES = 16 * 1024 * 1024
STATX_MNT_ID = 0x1000
STATX_MNT_ID_OFFSET = 144
PROC_SUPER_MAGIC = 0x9FA0
SYSFS_MAGIC = 0x62656572
CGROUP2_SUPER_MAGIC = 0x63677270


class MountRecord(NamedTuple):
    path: Path
    options: frozenset[str]
    filesystem_type: str
    source: str
    root: Path
    mount_id: int = 0


def _is_revision(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def package_digest(package_root: Path) -> str | None:
    try:
        root = package_root.resolve(strict=True)
        paths = sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix())
        digest = hashlib.sha256()
        for path in paths:
            relative = path.relative_to(root)
            if "__pycache__" in relative.parts or path.is_symlink():
                return None
            if path.is_dir():
                continue
            if not path.is_file():
                return None
            name = relative.as_posix().encode("utf-8")
            content = path.read_bytes()
            for field in (name, content):
                digest.update(len(field).to_bytes(8, "big"))
                digest.update(field)
    except (OSError, RuntimeError, UnicodeError):
        return None
    return "sha256:" + digest.hexdigest()


def installed_package_root() -> Path | None:
    try:
        specification = importlib.util.find_spec("oims")
        locations = tuple(specification.submodule_search_locations or ()) if specification else ()
        if len(locations) != 1:
            return None
        root = Path(locations[0]).resolve(strict=True)
        interpreter_prefix = Path(sys.prefix).resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError):
        return None
    workspace = Path("/workspace")
    if (
        sys.flags.isolated != 1
        or interpreter_prefix not in root.parents
        or workspace in root.parents
    ):
        return None
    return root


def _read_bounded_regular_bytes(path: Path, max_bytes: int) -> bytes | None:
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > max_bytes:
            return None
        payload = bytearray()
        while chunk := os.read(descriptor, max_bytes + 1 - len(payload)):
            payload.extend(chunk)
            if len(payload) > max_bytes:
                return None
        final_metadata = os.fstat(descriptor)
        if (
            len(payload) != metadata.st_size
            or final_metadata.st_dev != metadata.st_dev
            or final_metadata.st_ino != metadata.st_ino
            or final_metadata.st_size != metadata.st_size
            or final_metadata.st_mtime_ns != metadata.st_mtime_ns
        ):
            return None
        return bytes(payload)
    except (OSError, OverflowError):
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_values(path: Path) -> dict[str, str] | None:
    payload = _read_bounded_regular_bytes(path, MAX_ATTESTATION_BYTES)
    if payload is None:
        return None
    try:
        lines = payload.decode("ascii").splitlines()
    except UnicodeDecodeError:
        return None
    values: dict[str, str] = {}
    for line in lines:
        key, separator, value = line.partition("=")
        if not separator or key in values:
            return None
        values[key] = value
    return values


def _read_proc_metadata(path: Path) -> bytes | None:
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        proc_metadata = os.stat("/proc")
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_dev != proc_metadata.st_dev
            or _descriptor_filesystem_magic(descriptor) != PROC_SUPER_MAGIC
        ):
            return None
        payload = bytearray()
        while chunk := os.read(descriptor, MAX_PROC_METADATA_BYTES + 1 - len(payload)):
            payload.extend(chunk)
            if len(payload) > MAX_PROC_METADATA_BYTES:
                return None
        final_metadata = os.fstat(descriptor)
        if (
            final_metadata.st_dev != metadata.st_dev
            or final_metadata.st_ino != metadata.st_ino
            or final_metadata.st_mtime_ns != metadata.st_mtime_ns
        ):
            return None
        return bytes(payload)
    except (OSError, OverflowError):
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _descriptor_filesystem_magic(descriptor: int) -> int | None:
    try:
        fstatfs = ctypes.CDLL(None, use_errno=True).fstatfs
        fstatfs.argtypes = (ctypes.c_int, ctypes.c_void_p)
        fstatfs.restype = ctypes.c_int
        buffer = ctypes.create_string_buffer(256)
        if fstatfs(descriptor, buffer) != 0:
            return None
        return ctypes.c_ulong.from_buffer_copy(buffer.raw[: ctypes.sizeof(ctypes.c_ulong)]).value
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def _path_filesystem_magic(path: Path) -> int | None:
    descriptor: int | None = None
    try:
        flags = (
            getattr(os, "O_PATH", os.O_RDONLY)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(path, flags)
        return _descriptor_filesystem_magic(descriptor)
    except OSError:
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _mount_records(
    path: Path = MOUNTINFO_PATH,
) -> tuple[MountRecord, ...] | None:
    payload = _read_proc_metadata(path)
    if payload is None:
        return None
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return None
    records: list[MountRecord] = []
    for line in lines:
        before, separator, after = line.partition(" - ")
        fields = before.split()
        filesystem_fields = after.split()
        if (
            not separator
            or len(fields) < 6
            or len(filesystem_fields) < 2
            or not fields[0].isdigit()
        ):
            return None
        value = (
            fields[4]
            .replace("\\040", " ")
            .replace("\\011", "\t")
            .replace("\\012", "\n")
            .replace("\\134", "\\")
        )
        root = (
            fields[3]
            .replace("\\040", " ")
            .replace("\\011", "\t")
            .replace("\\012", "\n")
            .replace("\\134", "\\")
        )
        records.append(
            MountRecord(
                Path(value),
                frozenset(fields[5].split(",")),
                filesystem_fields[0],
                filesystem_fields[1],
                Path(root),
                int(fields[0]),
            )
        )
    return tuple(records)


def _path_mount_id(path: Path) -> int | None:
    try:
        statx = ctypes.CDLL(None, use_errno=True).statx
        statx.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_void_p,
        )
        statx.restype = ctypes.c_int
        buffer = ctypes.create_string_buffer(256)
        if statx(-100, os.fsencode(path), 0, STATX_MNT_ID, buffer) != 0:
            return None
        mask = struct.unpack_from("=I", buffer.raw, 0)[0]
        if mask & STATX_MNT_ID == 0:
            return None
        return struct.unpack_from("=Q", buffer.raw, STATX_MNT_ID_OFFSET)[0]
    except (AttributeError, OSError, struct.error, TypeError, ValueError):
        return None


def _mount_records_bind_current_namespace(records: tuple[MountRecord, ...]) -> bool:
    authenticated_paths = tuple(
        dict.fromkeys((MOUNTINFO_PATH, PROCESS_MAPS_PATH, *SANDBOX_OBSERVATION_PATHS))
    )
    for path in authenticated_paths:
        if path == Path("/sys/fs/cgroup") or Path("/sys/fs/cgroup") in path.parents:
            expected_filesystem_magic = CGROUP2_SUPER_MAGIC
        elif path == Path("/sys") or Path("/sys") in path.parents:
            expected_filesystem_magic = SYSFS_MAGIC
        else:
            expected_filesystem_magic = PROC_SUPER_MAGIC
        if _path_filesystem_magic(path) != expected_filesystem_magic:
            return False
        candidates = tuple(
            record
            for record in records
            if record.path == path or record.path == Path("/") or record.path in path.parents
        )
        if not candidates:
            return False
        maximum_depth = max(len(record.path.parts) for record in candidates)
        expected_mount_ids = {
            record.mount_id
            for record in candidates
            if len(record.path.parts) == maximum_depth and record.mount_id > 0
        }
        if _path_mount_id(path) not in expected_mount_ids:
            return False
    return True


def _mount_points(path: Path = MOUNTINFO_PATH) -> tuple[Path, ...] | None:
    records = _mount_records(path)
    return tuple(record[0] for record in records) if records is not None else None


def _native_runtime_root_paths() -> tuple[Path, ...] | None:
    roots: set[Path] = set()
    try:
        for candidate in NATIVE_RUNTIME_ROOTS:
            if not candidate.exists() and not candidate.is_symlink():
                continue
            roots.add(candidate)
            roots.add(candidate.resolve(strict=True))
    except (OSError, RuntimeError):
        return None
    return tuple(sorted(roots, key=str))


def _native_runtime_paths(path: Path = PROCESS_MAPS_PATH) -> tuple[Path, ...] | None:
    runtime_roots = _native_runtime_root_paths()
    if runtime_roots is None:
        return None
    protected: set[Path] = set(runtime_roots)

    def add_path(candidate: Path, *, required: bool) -> bool:
        try:
            if not required and not candidate.exists() and not candidate.is_symlink():
                return True
            if candidate.is_absolute() and candidate != Path("/proc/self/exe"):
                protected.add(candidate)
            protected.add(candidate.resolve(strict=True))
        except (OSError, RuntimeError):
            return False
        return True

    if not add_path(Path(sys.executable), required=True):
        return None
    if not add_path(Path("/proc/self/exe"), required=True):
        return None
    for candidate in DYNAMIC_LOADER_CONFIGURATION:
        if not add_path(candidate, required=False):
            return None

    payload = _read_proc_metadata(path)
    if payload is None:
        return None
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return None
    for line in lines:
        fields = line.split(maxsplit=5)
        if len(fields) < 5:
            return None
        if len(fields) != 6 or not fields[5].startswith("/"):
            continue
        mapped_path = fields[5]
        if mapped_path.endswith(" (deleted)") or not add_path(Path(mapped_path), required=True):
            return None
    return tuple(sorted(protected, key=str))


def _is_nvidia_runtime_path(path: Path) -> bool:
    executable_roots = {Path("/bin"), Path("/sbin"), Path("/usr/bin"), Path("/usr/sbin")}
    if path.parent in executable_roots:
        return path.name in NVIDIA_RUNTIME_EXECUTABLES
    library_roots = {Path("/lib"), Path("/lib64"), Path("/usr/lib"), Path("/usr/lib64")}
    if not any(root in path.parents for root in library_roots):
        return False
    name = path.name
    return ".so" in name and name.startswith(
        ("libcuda", "libnvidia", "libnvcuvid", "libGLX_nvidia", "libEGL_nvidia")
    )


def nvidia_runtime_approvals(
    path: Path = NVIDIA_RUNTIME_APPROVALS_PATH,
) -> dict[Path, str] | None:
    payload = _read_bounded_regular_bytes(path, MAX_NVIDIA_APPROVAL_BYTES)
    if payload is None:
        return None
    try:
        lines = payload.decode("ascii").splitlines()
    except UnicodeDecodeError:
        return None
    approvals: dict[Path, str] = {}
    for line in lines:
        if not line or line.startswith("#"):
            continue
        target, separator, digest = line.partition("=")
        candidate = Path(target)
        if (
            not separator
            or candidate in approvals
            or not candidate.is_absolute()
            or str(candidate) != target
            or ".." in candidate.parts
            or not _is_nvidia_runtime_path(candidate)
            or not _is_digest(digest)
        ):
            return None
        approvals[candidate] = digest
    return approvals or None


def nvidia_runtime_mount_attestation(
    records: tuple[tuple[Path, frozenset[str]], ...],
    approvals_path: Path = NVIDIA_RUNTIME_APPROVALS_PATH,
) -> tuple[tuple[Path, ...], str] | None:
    approvals = nvidia_runtime_approvals(approvals_path)
    if approvals is None:
        return None
    candidates = sorted(
        (record for record in records if _is_nvidia_runtime_path(record[0])),
        key=lambda record: str(record[0]),
    )
    if len(candidates) > MAX_NVIDIA_RUNTIME_MOUNTS:
        return None
    digest = hashlib.sha256(b"OIMS-NVIDIA-RUNTIME-MOUNTS-v1\0")
    allowed: list[Path] = []
    observed: set[Path] = set()
    total_bytes = 0
    for record in candidates:
        path, options = record[0], record[1]
        if path in observed or "ro" not in options or "rw" in options:
            return None
        observed.add(path)
        descriptor: int | None = None
        try:
            flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                return None
            encoded_path = str(path).encode("utf-8")
            digest.update(len(encoded_path).to_bytes(8, "big"))
            digest.update(encoded_path)
            digest.update(metadata.st_size.to_bytes(8, "big"))
            file_digest = hashlib.sha256()
            file_bytes = 0
            while chunk := os.read(descriptor, 1024 * 1024):
                file_bytes += len(chunk)
                total_bytes += len(chunk)
                if total_bytes > MAX_NVIDIA_RUNTIME_BYTES:
                    return None
                digest.update(chunk)
                file_digest.update(chunk)
            final_metadata = os.fstat(descriptor)
            if (
                file_bytes != metadata.st_size
                or final_metadata.st_dev != metadata.st_dev
                or final_metadata.st_ino != metadata.st_ino
                or final_metadata.st_size != metadata.st_size
                or final_metadata.st_mtime_ns != metadata.st_mtime_ns
            ):
                return None
            if approvals.get(path) != "sha256:" + file_digest.hexdigest():
                return None
        except (OSError, OverflowError, UnicodeError):
            return None
        finally:
            if descriptor is not None:
                os.close(descriptor)
        allowed.append(path)
    return tuple(allowed), "sha256:" + digest.hexdigest()


def attested_nvidia_smi_path(paths: tuple[Path, ...]) -> Path | None:
    candidates = tuple(path for path in paths if path.name == "nvidia-smi")
    return candidates[0] if len(candidates) == 1 else None


def _cgroup_membership(path: Path = Path("/proc/self/cgroup")) -> str | None:
    payload = _read_proc_metadata(path)
    if payload is None:
        return None
    try:
        lines = payload.decode("ascii").splitlines()
    except UnicodeDecodeError:
        return None
    return "/" if lines == ["0::/"] else None


def sandbox_observation_mount_errors(
    records: tuple[MountRecord, ...],
    cgroup_membership: str | None,
) -> tuple[str, ...]:
    for root, expected_filesystems in OBSERVATION_ROOT_FILESYSTEMS.items():
        root_records = tuple(record for record in records if record.path == root)
        if (
            len(root_records) != 1
            or root_records[0].filesystem_type not in expected_filesystems
            or root_records[0].root != Path("/")
        ):
            return ("Forge sandbox observation filesystems cannot be verified",)
    if cgroup_membership != "/":
        return ("Forge sandbox cgroup membership cannot be verified",)
    allowed_roots = set(OBSERVATION_ROOT_FILESYSTEMS)
    for record in records:
        mount = record.path
        if mount == Path("/") or mount in allowed_roots:
            continue
        if any(
            mount == target or mount in target.parents or target in mount.parents
            for target in SANDBOX_OBSERVATION_PATHS
        ):
            return ("Forge sandbox observation sources contain an unexpected mount",)
    return ()


def protected_mount_errors(
    package_root: Path,
    attestation_path: Path = ATTESTATION_PATH,
    verifier_path: Path | None = None,
    observed_mounts: tuple[Path, ...] | None = None,
    interpreter_prefix: Path | None = None,
    native_runtime_paths: tuple[Path, ...] | None = None,
    native_runtime_roots: tuple[Path, ...] | None = None,
    allowed_native_mounts: tuple[Path, ...] = (),
    nvidia_approvals_path: Path = NVIDIA_RUNTIME_APPROVALS_PATH,
    observed_mount_records: tuple[MountRecord, ...] | None = None,
    protect_sandbox_observations: bool = False,
    cgroup_membership: str | None = None,
) -> tuple[str, ...]:
    if protect_sandbox_observations:
        if observed_mount_records is None:
            return ("Forge sandbox observation filesystems cannot be verified",)
        observation_errors = sandbox_observation_mount_errors(
            observed_mount_records,
            cgroup_membership,
        )
        if observation_errors:
            return observation_errors
    runtime_paths = (
        native_runtime_paths if native_runtime_paths is not None else _native_runtime_paths()
    )
    if runtime_paths is None:
        return ("Forge native executable runtime cannot be verified",)
    runtime_roots = (
        native_runtime_roots if native_runtime_roots is not None else _native_runtime_root_paths()
    )
    if runtime_roots is None:
        return ("Forge native executable runtime cannot be verified",)
    try:
        approval_targets = (
            (nvidia_approvals_path.resolve(strict=True),)
            if nvidia_approvals_path.exists() or nvidia_approvals_path.is_symlink()
            else ()
        )
        core_protected = (
            package_root.resolve(strict=True),
            attestation_path.resolve(strict=True),
            (verifier_path or Path(__file__)).resolve(strict=True),
            (interpreter_prefix or Path(sys.prefix)).resolve(strict=True),
            *approval_targets,
            *(target for target in runtime_paths if target not in runtime_roots),
        )
    except (OSError, RuntimeError):
        return ("Forge protected source paths cannot be resolved",)
    mounts = observed_mounts if observed_mounts is not None else _mount_points()
    if mounts is None:
        return ("Forge runtime mount topology cannot be verified",)
    filesystem_root = Path("/")
    for mount in mounts:
        if mount == filesystem_root:
            continue
        intersects_core = any(
            mount == target or mount in target.parents or target in mount.parents
            for target in core_protected
        )
        intersects_runtime_root = any(
            mount == target or mount in target.parents or target in mount.parents
            for target in runtime_roots
        )
        if intersects_core or (intersects_runtime_root and mount not in allowed_native_mounts):
            return ("Forge protected executable runtime contains an unexpected mount",)
    return ()


def verify_installed_package(
    attestation_path: Path = ATTESTATION_PATH,
    package_root: Path | None = None,
    observed_mounts: tuple[Path, ...] | None = None,
    allowed_native_mounts: tuple[Path, ...] = (),
    observed_mount_records: tuple[MountRecord, ...] | None = None,
    protect_sandbox_observations: bool = False,
    cgroup_membership: str | None = None,
) -> tuple[str, ...]:
    values = _read_values(attestation_path)
    if values is None or set(values) != {"commit", "tree", "package_sha256"}:
        return ("Forge source attestation is missing or malformed",)
    if not _is_revision(values["commit"]) or not _is_revision(values["tree"]):
        return ("Forge source attestation revisions are malformed",)
    if not _is_digest(values["package_sha256"]):
        return ("Forge installed-package attestation is malformed",)
    root = package_root if package_root is not None else installed_package_root()
    if root is None:
        return ("Forge installed package is not isolated from runtime shadowing",)
    mount_errors = protected_mount_errors(
        root,
        attestation_path,
        observed_mounts=observed_mounts,
        allowed_native_mounts=allowed_native_mounts,
        observed_mount_records=observed_mount_records,
        protect_sandbox_observations=protect_sandbox_observations,
        cgroup_membership=cgroup_membership,
    )
    if mount_errors:
        return mount_errors
    observed = package_digest(root)
    if observed != values["package_sha256"]:
        return ("Forge installed package does not match its build attestation",)
    return ()


def seal_attestation(attestation_path: Path = ATTESTATION_PATH) -> int:
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        print("Forge attestation sealing requires the image-build root user", file=sys.stderr)
        return 70
    values = _read_values(attestation_path)
    if values is None or set(values) != {"commit", "tree"}:
        print("Forge source attestation is missing or malformed", file=sys.stderr)
        return 70
    if not _is_revision(values["commit"]) or not _is_revision(values["tree"]):
        print("Forge source attestation revisions are malformed", file=sys.stderr)
        return 70
    root = installed_package_root()
    observed = package_digest(root) if root is not None else None
    if observed is None:
        print("Forge installed package cannot be attested", file=sys.stderr)
        return 70
    mount_errors = protected_mount_errors(root, attestation_path)
    if mount_errors:
        for error in mount_errors:
            print(error, file=sys.stderr)
        return 70
    try:
        with attestation_path.open("a", encoding="ascii", newline="\n") as handle:
            handle.write(f"package_sha256={observed}\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        print(f"cannot seal Forge installed-package attestation: {exc}", file=sys.stderr)
        return 70
    return 0


def main(arguments: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if arguments is None else arguments)
    if argv == ["--seal-attestation"]:
        return seal_attestation()
    os.environ.pop(NVIDIA_RUNTIME_ATTESTATION_ENV, None)
    os.environ.pop(NVIDIA_SMI_PATH_ENV, None)
    records = _mount_records()
    if records is None or not _mount_records_bind_current_namespace(records):
        errors = ("Forge runtime mount topology cannot be verified",)
        nvidia_attestation = None
        nvidia_smi_path = None
    elif argv[:2] == ["forge", "probe"]:
        nvidia_attestation = nvidia_runtime_mount_attestation(records)
        cgroup_membership = _cgroup_membership()
        nvidia_smi_path = (
            attested_nvidia_smi_path(nvidia_attestation[0])
            if nvidia_attestation is not None
            else None
        )
        errors = (
            ("Forge NVIDIA runtime mounts cannot be attested",)
            if nvidia_attestation is None or nvidia_smi_path is None
            else verify_installed_package(
                observed_mounts=tuple(record[0] for record in records),
                allowed_native_mounts=nvidia_attestation[0],
                observed_mount_records=records,
                protect_sandbox_observations=True,
                cgroup_membership=cgroup_membership,
            )
        )
    elif argv[:2] == ["forge", "simulate"]:
        nvidia_attestation = None
        nvidia_smi_path = None
        errors = verify_installed_package(
            observed_mounts=tuple(record[0] for record in records),
            observed_mount_records=records,
            protect_sandbox_observations=True,
            cgroup_membership=_cgroup_membership(),
        )
    else:
        nvidia_attestation = None
        nvidia_smi_path = None
        errors = verify_installed_package(observed_mounts=tuple(record[0] for record in records))
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 70
    if nvidia_attestation is not None and nvidia_smi_path is not None:
        os.environ[NVIDIA_RUNTIME_ATTESTATION_ENV] = nvidia_attestation[1]
        os.environ[NVIDIA_SMI_PATH_ENV] = str(nvidia_smi_path)
    os.execv(sys.executable, [sys.executable, "-I", "-m", "oims", *argv])
    return 70


if __name__ == "__main__":
    raise SystemExit(main())
