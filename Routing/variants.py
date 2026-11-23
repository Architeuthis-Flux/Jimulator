# SPDX-License-Identifier: MIT
"""Variants: which firmware src/ tree the harness is built from.

A variant is a complete src/ tree. It comes from the firmware checkout
("worktree"), from another checkout (a directory that holds src/), from a git
ref of the firmware checkout, or from any of those with some files replaced.
Each is identified by a hash of its sources and of the harness, and built
once into build/bin/<hash>/.

The firmware checkout (REPO) is JumperlOS: this repository's own submodule,
or the checkout the JUMPERLOS environment variable names (a working copy
whose router is being changed, say). The lab reads two things from it: the
router's source (src/) and the bench suite's fabric and judge (JumperlOS/test/hil/,
which importing this module puts on the path).
"""
import hashlib
import io
import os
import posixpath
import shutil
import subprocess
import sys
import tarfile
import threading
from dataclasses import dataclass
from pathlib import Path

LAB = Path(__file__).resolve().parent
REPO = Path(os.environ.get("JUMPERLOS") or LAB.parent / "JumperlOS").expanduser().resolve()
HIL = REPO / "test" / "hil"
if not (REPO / "src").is_dir() or not (HIL / "fabric_v5.py").is_file():
    raise SystemExit("The firmware is not at %s.\nFetch this repository's copy:   git submodule update --init\n"
                     "or name a JumperlOS checkout:    JUMPERLOS=/path/to/JumperlOS python3 Routing/lab.py ..." % REPO)
if str(HIL) not in sys.path:
    sys.path.append(str(HIL))               # after the lab's own modules: a name both have is the lab's
HARNESS_DIR = LAB / "harness"
BUILD_DIR = LAB / "build"
SOURCE_SUFFIXES = (".h", ".hpp", ".cpp")

_build_lock = threading.Lock()
_materialize_lock = threading.Lock()      # one thread at a time unpacks or copies a variant tree


class BuildError(Exception):
    """The harness did not compile or link. .stderr is the compiler's output."""

    def __init__(self, stderr):
        self.stderr = stderr
        lines = [line for line in stderr.splitlines() if line.strip()]
        first = next((line for line in lines if "error" in line), lines[0] if lines else "build failed")
        super().__init__(first)


@dataclass(frozen=True)
class Variant:
    name: str
    src_root: Path
    hash: str


def safe_override_path(rel):
    """Normalise an override's path; ValueError unless it stays under src/."""
    if not rel or rel.startswith(("/", "\\")):
        raise ValueError("override path must be relative and under src/: %r" % rel)
    norm = posixpath.normpath(rel.replace("\\", "/"))
    if not norm.startswith("src/") or ".." in norm.split("/"):
        raise ValueError("override path must stay under src/: %r" % rel)
    return norm


def _update_with_tree(h, root, suffixes=None):
    for path in sorted(p for p in Path(root).rglob("*") if p.is_file()):
        if suffixes and path.suffix not in suffixes:
            continue
        h.update(path.relative_to(root).as_posix().encode())
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")


def _hash(src_root):
    # The compiler flags live in harness/build.sh, so hashing the harness
    # directory covers them along with the harness and its stubs.
    h = hashlib.sha256()
    _update_with_tree(h, src_root, SOURCE_SUFFIXES)
    h.update(b"--harness--")
    _update_with_tree(h, HARNESS_DIR)
    return h.hexdigest()


def harness_hash():
    """Identifies the harness alone (its sources, stubs and build flags): what
    a fidelity pass against a board capture vouches for."""
    h = hashlib.sha256()
    _update_with_tree(h, HARNESS_DIR)
    return h.hexdigest()


def _scratch_name(dest):
    return dest.with_name("%s.tmp%d-%d" % (dest.name, os.getpid(), threading.get_ident()))


def _git_ref_tree(spec):
    p = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify", "--quiet", "--end-of-options",
                        spec + "^{commit}"], capture_output=True, text=True)
    if p.returncode != 0:
        shallow = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--is-shallow-repository"],
                                 capture_output=True, text=True).stdout.strip() == "true"
        raise ValueError("not a directory holding src/ and not a git ref: %r%s" % (
            spec, " (the firmware checkout at %s is shallow; for its history: git -C %s fetch --unshallow)"
            % (REPO, REPO) if shallow else ""))
    sha = p.stdout.strip()
    dest = BUILD_DIR / "variants" / ("ref-" + sha[:12])
    with _materialize_lock:
        if not (dest / "src").is_dir():
            p = subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", sha, "src"], capture_output=True)
            if p.returncode != 0:
                raise ValueError("%s (%s) has no src/ to build" % (spec, sha[:7]))
            tmp = _scratch_name(dest)
            shutil.rmtree(tmp, ignore_errors=True)
            try:
                tmp.mkdir(parents=True)
                with tarfile.open(fileobj=io.BytesIO(p.stdout)) as archive:
                    archive.extractall(tmp, filter="data")
                shutil.rmtree(dest, ignore_errors=True)
                tmp.rename(dest)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)      # gone already after a good rename
    return "%s@%s" % (spec, sha[:7]), dest / "src"


def resolve(spec, overrides=None, *, allow_directory=True):
    """A Variant for "worktree", a directory that holds src/, or a git ref,
    optionally with files replaced ({"src/...": bytes}). With
    allow_directory=False a spec is "worktree" or a git ref and nothing else
    (the server decides which directories may be named)."""
    if spec == "worktree":
        name, src_root = "worktree", REPO / "src"
    elif allow_directory and (Path(spec).expanduser() / "src").is_dir():
        name, src_root = spec, Path(spec).expanduser().resolve() / "src"
    else:
        name, src_root = _git_ref_tree(spec)
    if overrides:
        files = {safe_override_path(rel): data for rel, data in overrides.items()}
        digest = hashlib.sha256()
        for rel in sorted(files):
            digest.update(rel.encode() + b"\0" + files[rel] + b"\0")
        dest = BUILD_DIR / "variants" / ("ovr-%s-%s" % (_hash(src_root)[:12], digest.hexdigest()[:12]))
        with _materialize_lock:
            if not (dest / "src").is_dir():
                tmp = _scratch_name(dest)
                shutil.rmtree(tmp, ignore_errors=True)
                try:
                    shutil.copytree(src_root, tmp / "src")
                    for rel, data in files.items():
                        target = tmp / rel
                        try:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_bytes(data)
                        except OSError as e:        # the path is a directory, or runs through a file
                            raise ValueError("cannot put a file at %s: %s" % (rel, e.strerror)) from None
                    shutil.rmtree(dest, ignore_errors=True)
                    tmp.rename(dest)
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)  # gone already after a good rename
        name = "%s + %d file%s" % (name, len(files), "" if len(files) == 1 else "s")
        src_root = dest / "src"
    return Variant(name, src_root, _hash(src_root))


def build(v, sanitize=True):
    """The harness binary for a variant, built once. Raises BuildError."""
    out = BUILD_DIR / "bin" / v.hash / ("lab_harness" if sanitize else "lab_harness_nosan")
    with _build_lock:
        if out.exists():
            return out
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = _scratch_name(out)
        env = dict(os.environ, SANITIZE="1" if sanitize else "0")
        p = subprocess.run([str(HARNESS_DIR / "build.sh"), str(v.src_root), str(tmp)],
                           capture_output=True, text=True, env=env)
        shutil.rmtree(str(tmp) + ".obj", ignore_errors=True)
        error = None
        if p.returncode != 0:
            error = p.stderr or p.stdout
        elif BUILD_DIR not in v.src_root.parents and _hash(v.src_root) != v.hash:
            # A live checkout was hashed at resolve() and compiled just now. If
            # a file was saved in between, this binary is not the one the hash
            # names, and filing it there would hand it to every later run.
            error = "the sources changed while the harness was building; run again"
        if error:
            tmp.unlink(missing_ok=True)
            if not any(out.parent.iterdir()):
                out.parent.rmdir()
            raise BuildError(error)
        os.replace(tmp, out)
        return out
