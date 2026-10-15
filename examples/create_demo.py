"""Create small metadata fixtures for trying the CLI; never extract them."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main() -> None:
    destination = Path(__file__).resolve().parents[1] / ".local" / "demo"
    destination.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination / "clean.zip", "w", ZIP_DEFLATED) as archive:
        archive.writestr("docs/readme.txt", "hello")
        archive.writestr("data/sample.csv", "x,y\n1,2\n")
    with ZipFile(destination / "problematic.zip", "w") as archive:
        archive.writestr("data/CON.csv", "hello")
        archive.writestr("Docs/a.txt", "hello")
        archive.writestr("docs/b.txt", "hello")
    print(f"Created demo ZIP files in {destination}")


if __name__ == "__main__":
    main()
