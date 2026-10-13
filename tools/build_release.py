"""Build, smoke check and zip a clean Windows portable release."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_version import APP_VERSION

MODEL_HASH = "6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command, *, log: Path | None = None, **kwargs):
    if log:
        with log.open("w", encoding="utf-8") as stream:
            subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                           check=True, **kwargs)
    else:
        subprocess.run(command, cwd=ROOT, check=True, **kwargs)


def package_release():
    dist = ROOT / "dist"
    work = ROOT / "build"
    application = dist / "NRrelics"
    exe = application / "NRrelic_Bot.exe"
    assert exe.is_file(), "Build the executable first"
    import win32api
    assert win32api.GetFileVersionInfo(str(exe), "\\StringFileInfo\\040904B0\\ProductVersion") == APP_VERSION
    models = list((application / "_internal/resources/models").glob("*.onnx"))
    assert [path.name for path in models] == ["PP-OCRv6_rec_small.onnx"]
    assert sha256(models[0]) == MODEL_HASH, "Bundled model hash mismatch"
    assert not (application / "data").exists(), "User data must not be in the build"
    for name in ("logs", "debug", "debug_ocr"):
        assert not (application / name).exists(), f"Unexpected personal files: {name}"

    # Test a disposable copy so startup cannot add settings to the release.
    check_report = work / f"release-check-{APP_VERSION}.json"
    with tempfile.TemporaryDirectory(prefix="release-smoke-", dir=work) as temporary:
        copied = Path(temporary) / "NRrelics"
        shutil.copytree(application, copied)
        environment = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        run([str(copied / exe.name), "--self-test", str(check_report)],
            env=environment, timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
    check = json.loads(check_report.read_text(encoding="utf-8"))
    assert check["ok"] and check["frozen"] and check["version"] == APP_VERSION

    # Ship user documentation and upstream license files beside the program.
    shutil.copy2(ROOT / "README.md", application / "README.md")
    shutil.copytree(ROOT / "docs", application / "docs", dirs_exist_ok=True)
    licenses = application / "licenses"
    for name in ("rapidocr", "onnxruntime", "opencv-python", "Pillow", "numpy",
                 "PySide6", "shiboken6", "PySide6-Fluent-Widgets", "cryptography",
                 "rapidfuzz", "pywin32", "pyautogui", "pydirectinput", "keyboard",
                 "pygetwindow", "pyclipper", "shapely", "omegaconf", "requests",
                 "PyYAML", "certifi", "charset-normalizer", "urllib3", "idna",
                 "coloredlogs", "humanfriendly", "flatbuffers", "protobuf",
                 "tqdm", "darkdetect", "PyRect", "MouseInfo", "PyScreeze", "PyTweening"):
        try:
            distribution = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        for file in distribution.files or ():
            parts = Path(str(file)).parts
            if (any(part.lower() in ("license", "licenses", "license.txt", "license.md",
                                     "copying", "notice", "notice.txt") for part in parts)
                    and distribution.locate_file(file).is_file()):
                target = licenses / name / Path(*parts[1:])
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(distribution.locate_file(file), target)

    manifest = {"version": APP_VERSION, "platform": "windows-x64",
                "python": sys.version, "checks": check,
                "packages": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
                "files": {path.relative_to(application).as_posix(): sha256(path)
                          for path in sorted(application.rglob("*")) if path.is_file()}}
    (application / "release-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    archive = dist / f"NRrelics-{APP_VERSION}-windows-x64.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as package:
        for path in sorted(application.rglob("*")):
            if path.is_file():
                package.write(path, "NRrelics/" + path.relative_to(application).as_posix())
    with zipfile.ZipFile(archive) as package:
        assert package.testzip() is None, "Release ZIP failed its CRC check"
    checksum = sha256(archive)
    archive.with_suffix(".zip.sha256").write_text(f"{checksum}  {archive.name}\n", encoding="ascii")
    print(f"Release ready: {archive} ({archive.stat().st_size / 1024**2:.1f} MiB)")
    print(f"SHA256: {checksum}")
    print(f"Smoke report: {check_report}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-only", action="store_true", help="Check and zip an existing build")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Windows is required for this build")
    for directory in (ROOT / "build", ROOT / "dist"):
        resolved = directory.resolve()
        if not resolved.is_relative_to(ROOT.resolve()):
            parser.error(f"Build directory resolves outside the workspace: {resolved}")
        directory.mkdir(exist_ok=True)
    if not args.package_only:
        run([sys.executable, "-m", "pip", "check"])
        run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"])
        run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "NRrelic_Bot.spec"],
            log=ROOT / "build" / f"pyinstaller-{APP_VERSION}.log")
    package_release()


if __name__ == "__main__":
    main()
