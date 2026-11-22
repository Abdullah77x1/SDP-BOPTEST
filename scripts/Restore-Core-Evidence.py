"""Restore original members for a selected prefix from the larger verified ZIP."""
from argparse import ArgumentParser
from hashlib import file_digest, sha256
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

parser = ArgumentParser(description=__doc__)
parser.add_argument("source_zip", type=Path)
parser.add_argument("member_prefix", help="Original relative path or directory prefix")
parser.add_argument("destination", type=Path, help="A separate review copy or empty directory")
args = parser.parse_args()
parent = "SDP_BOPTEST_TEAM_PACKAGE/"
with args.source_zip.open("rb") as archive:
    if file_digest(archive, "sha256").hexdigest() != "106589797dc7f98f80466abd64006a02213c387c2777e38e65d9f60cd04817db":
        raise ValueError("The source does not match the original BOPTEST-only ZIP.")
prefix = args.member_prefix.replace("\\", "/").strip("/")
if not prefix:
    raise ValueError("Choose a specific original path or directory.")
root = args.destination.resolve()
count = 0
with ZipFile(args.source_zip) as archive:
    for entry in archive.namelist():
        if not entry.startswith(parent):
            continue
        name = entry.removeprefix(parent)
        if name != prefix and not name.startswith(prefix + "/"):
            continue
        target = (root / Path(*PurePosixPath(name).parts)).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"Unsafe source member: {name}")
        data = archive.read(entry)
        if target.is_file():
            if sha256(target.read_bytes()).digest() != sha256(data).digest():
                raise FileExistsError(target)
        else:
            target.parent.mkdir(exist_ok=True, parents=True)
            with target.open("xb") as file:
                file.write(data)
        count += 1
if not count:
    raise FileNotFoundError(prefix)
print(f"Restored or verified {count} original members.")
