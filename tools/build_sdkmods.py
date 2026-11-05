"""
Packs every mod folder into dist/<mod>.sdkmod, ready to drop into the game's sdk_mods folder.

Usage: python tools/build_sdkmods.py
"""

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
LICENSE = ROOT / "LICENSE"

def build(mod_dir: Path) -> Path:
    out = DIST / f"{mod_dir.name}.sdkmod"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(mod_dir.rglob("*")):
            if file.is_dir() or "__pycache__" in file.parts:
                continue
            zf.write(file, file.relative_to(ROOT).as_posix())
        if not (mod_dir / "LICENSE").exists():
            zf.write(LICENSE, f"{mod_dir.name}/LICENSE")
    return out

def main() -> None:
    DIST.mkdir(exist_ok=True)
    for mod_dir in sorted(ROOT.iterdir()):
        if (mod_dir / "__init__.py").exists() and (mod_dir / "pyproject.toml").exists():
            print(f"built {build(mod_dir).relative_to(ROOT)}")

if __name__ == "__main__":
    main()
