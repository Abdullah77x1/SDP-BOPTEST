"""Verify the frozen GitHub assets and restore sealed histories at their original paths."""
from hashlib import file_digest, sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
import json
import tarfile

root = Path(__file__).resolve().parents[1]
descriptor = json.loads((root / "assets/ASSETS.json").read_bytes())


def local(relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Unsafe core asset path: {relative}")
    return path


def digest(path):
    with path.open("rb") as file:
        return file_digest(file, "sha256").hexdigest()


def verified_blob(section):
    source = local(section["source"])
    if digest(source) != section["encoded_sha256"]:
        raise ValueError(f"Bundled asset hash differs: {source.name}")
    return source


def materialize(path, contents, expected):
    if sha256(contents).hexdigest() != expected:
        raise ValueError(f"Restored bytes differ from frozen evidence: {path.name}")
    if path.exists():
        if digest(path) != expected:
            raise FileExistsError(f"Existing asset differs: {path}")
        return
    path.parent.mkdir(exist_ok=True, parents=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(contents)
        staged = Path(temporary.name)
    try:
        # On Windows rename fails if the target already exists. Verify it if a
        # concurrent setup created it first.
        try:
            staged.rename(path)
        except FileExistsError:
            if digest(path) != expected:
                raise
    finally:
        staged.unlink(missing_ok=True)


model = descriptor["model"]
target = local(model["target"])
if not target.is_file() or target.stat().st_size != model["bytes"] or digest(target) != model["sha256"]:
    raise ValueError("The frozen O25 checkpoint is missing or differs from its expected hash. "
                     "Install Git LFS, then run 'git lfs pull' from the checkout root.")
print("Verified original O25 checkpoint.")

fmu = descriptor["fmu"]
target = local(fmu["target"])
if not target.is_file() or digest(target) != fmu["sha256"]:
    raise ValueError("The pinned BESTEST Air FMU is missing or differs from its frozen hash.")
print("Verified pinned BESTEST Air FMU.")

for key, label in (("history", "G218 evidence"), ("calibration", "calibration and rolling evidence")):
    history = descriptor[key]
    expected = history["members"]
    seen = set()
    with tarfile.open(verified_blob(history), "r|xz") as bundle:
        for entry in bundle:
            if not entry.isfile() or entry.name not in expected or entry.name in seen:
                raise ValueError(f"Unexpected history member: {entry.name}")
            with bundle.extractfile(entry) as source:
                materialize(local(entry.name), source.read(), expected[entry.name])
            seen.add(entry.name)
    if seen != set(expected):
        raise ValueError(f"Restore is incomplete for {label}.")
    print(f"Verified {len(seen):,} original {label} files.")
print("Core assets are ready.")
