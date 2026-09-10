"""Download and safely extract the remaining official TAT-DQA PDF splits."""
import argparse
from pathlib import Path
from zipfile import ZipFile
import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits", nargs="+", choices=["train", "dev", "test"], default=["dev", "test"])
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parents[1] / "data")
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    for split in args.splits:
        name = f"tatdqa_docs_{split}"
        archive = args.directory / f"{name}.zip"
        if not archive.exists():
            partial = archive.with_suffix(".zip.part")
            url = f"https://huggingface.co/datasets/next-tat/TAT-DQA/resolve/main/{name}.zip"
            print(f"Downloading {name}", flush=True)
            with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
                response.raise_for_status()
                with partial.open("wb") as stream:
                    for chunk in response.iter_bytes(1024 * 1024):
                        stream.write(chunk)
            partial.replace(archive)
        destination = (args.directory / name).resolve()
        with ZipFile(archive) as zipped:
            for member in zipped.infolist():
                target = (destination / member.filename).resolve()
                if not target.is_relative_to(destination):
                    raise ValueError(f"Unsafe archive path: {member.filename}")
            zipped.extractall(destination)
        print(f"Ready: {destination}", flush=True)


if __name__ == "__main__":
    main()
