#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Windows build helper for AirfoilEditor.

This script replaces complex batch logic with a small, readable Python driver.
It supports:
- building the PyInstaller onedir bundle
- optionally creating a zip from the bundle
- building the NSIS installer
- running all steps in sequence
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path


APP_NAME = "AirfoilEditor"
DESCRIPTION = "An interactive airfoil design and analysis tool"
ICON_NAME = "AE.ico"
DIST_DIR_NAME = "dist"


def _run(cmd: list[str], cwd: Path, capture_output: bool = False) -> str:
    print(f"> {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=capture_output,
        check=False,
    )
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {' '.join(cmd)}")
    return result.stdout.strip() if capture_output else ""


def _project_metadata(repo_root: Path) -> tuple[str, str]:
    package_name = _run(["hatch", "project", "metadata", "name"], cwd=repo_root, capture_output=True)
    package_version = _run(["hatch", "project", "metadata", "version"], cwd=repo_root, capture_output=True)
    return package_name, package_version


def _remove_dir_if_exists(path: Path, attempts: int = 6, delay_s: float = 0.8) -> None:
    for i in range(1, attempts + 1):
        try:
            if not path.exists():
                return
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            print(f"Remove attempt {i}/{attempts} failed (permission denied), retrying...")
            time.sleep(delay_s)

    if path.exists():
        shutil.rmtree(path)


def _replace_dir_with_retry(src: Path, dst: Path, attempts: int = 6, delay_s: float = 0.8) -> None:
    last_exc: Exception | None = None

    for i in range(1, attempts + 1):
        try:
            _remove_dir_if_exists(dst, attempts=1, delay_s=delay_s)
            src.rename(dst)
            return
        except FileNotFoundError as exc:
            last_exc = exc
            if not src.exists():
                raise RuntimeError(f"Build output source folder disappeared: {src}") from exc
            print(f"Rename attempt {i}/{attempts} failed (path race), retrying...")
            time.sleep(delay_s)
        except PermissionError as exc:
            last_exc = exc
            print(f"Rename attempt {i}/{attempts} failed (permission denied), retrying...")
            time.sleep(delay_s)

    try:
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        shutil.rmtree(src)
        return
    except Exception as exc:
        if last_exc is not None:
            raise RuntimeError(f"Failed to move build output after retries: {last_exc}") from exc
        raise


def _run_pytest(repo_root: Path, mode: str) -> None:
    if mode == "none":
        return
    if mode == "not-slow":
        _run(["pytest", "tests", "-m", "not slow"], cwd=repo_root)
    elif mode == "all":
        _run(["pytest", "tests"], cwd=repo_root)
    else:
        raise ValueError(f"Unsupported test mode: {mode}")


def build_exe(repo_root: Path, *, test_mode: str = "none") -> None:
    package_name, package_version = _project_metadata(repo_root)

    dist_dir = repo_root / DIST_DIR_NAME
    pyinstaller_out = dist_dir / APP_NAME
    win_exe_dir = f"{package_name}-{package_version}_win_exe"
    final_out = dist_dir / win_exe_dir

    print()
    print("------ Create Windows exe using PyInstaller")
    print(f"App             : {APP_NAME}")
    print(f"Icon            : {ICON_NAME}")
    print(f"Package name    : {package_name}")
    print(f"Package version : {package_version}")
    print(f"Output folder   : {win_exe_dir}")

    print()
    print(f"------ Pytest ({test_mode})")
    _run_pytest(repo_root, test_mode)

    icon_path = repo_root / "icons" / ICON_NAME
    if not icon_path.is_file():
        raise FileNotFoundError(f"Icon not found: {icon_path}")

    worker_exe = repo_root / "assets" / "windows" / "worker.exe"
    if not worker_exe.is_file():
        raise FileNotFoundError(f"Missing required asset: {worker_exe}")

    xo2_exe = repo_root / "assets" / "windows" / "xoptfoil2.exe"
    if not xo2_exe.is_file():
        raise FileNotFoundError(f"Missing required asset: {xo2_exe}")

    print()
    print("------ PyInstaller build")

    _remove_dir_if_exists(pyinstaller_out)

    _run(
        [
            "pyinstaller",
            "--noconfirm",
            "--log-level=INFO",
            "--onedir",
            "--noconsole",
            "--distpath",
            DIST_DIR_NAME,
            "--icon",
            "./icons/AE.ico",
            "--paths",
            package_name,
            "--add-data",
            f"./icons;{package_name}/icons",
            "--add-data",
            f"./assets/windows/worker.exe;{package_name}/assets/windows",
            "--add-data",
            f"./assets/windows/xoptfoil2.exe;{package_name}/assets/windows",
            "--add-data",
            f"./examples_optimize;{package_name}/examples_optimize",
            "--exclude-module",
            "matplotlib",
            "--exclude-module",
            "numpy.tests",
            "--exclude-module",
            "PyQt6.QtWebEngine",
            "--exclude-module",
            "charset_normalizer.md__mypyc",
            "--runtime-tmpdir",
            "mySuperTemp",
            "-n",
            APP_NAME,
            f"{package_name}.py",
        ],
        cwd=repo_root,
    )

    if not pyinstaller_out.exists():
        raise FileNotFoundError(f"PyInstaller output not found: {pyinstaller_out}")

    readme_pdf = repo_root / "README.pdf"
    if readme_pdf.exists():
        shutil.copy2(readme_pdf, pyinstaller_out / "README.pdf")

    _remove_dir_if_exists(final_out)
    _replace_dir_with_retry(pyinstaller_out, final_out)

    print()
    print("------ Exe build finished successfully")
    print(f"Created: {final_out}")

def build_installer(repo_root: Path) -> None:
    package_name, package_version = _project_metadata(repo_root)

    win_exe_dir = f"{package_name}-{package_version}_win_exe"
    installer_name = f"{package_name}-{package_version}_win_setup.exe"

    bundle_dir = repo_root / DIST_DIR_NAME / win_exe_dir
    app_exe = bundle_dir / f"{APP_NAME}.exe"

    print()
    print("------ Create Windows installer")
    print(f"App             : {APP_NAME}")
    print(f"Package name    : {package_name}")
    print(f"Package version : {package_version}")
    print(f"Bundle folder   : {bundle_dir}")
    print(f"Installer name  : {installer_name}")

    if not app_exe.exists():
        raise FileNotFoundError(f"PyInstaller output not found: {app_exe}")

    if shutil.which("makensis") is None and shutil.which("makensis.exe") is None:
        raise FileNotFoundError("makensis.exe not found in PATH")

    _run(
        [
            "makensis.exe",
            "/V3",
            f"/DVERSION={package_version}",
            f"/DAPP_NAME={APP_NAME}",
            f"/DPACKAGE_NAME={package_name}",
            f"/DWIN_EXE_DIR={win_exe_dir}",
            f"/DDESCRIPTION={DESCRIPTION}",
            f"/DICON_NAME={ICON_NAME}",
            f"/DINSTALLER_NAME={installer_name}",
            "dev\\win_installer.nsi",
        ],
        cwd=repo_root,
    )

    print()
    print("------ Installer finished successfully")
    print(f"Created: {repo_root / DIST_DIR_NAME / installer_name}")


def _repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Windows build helper for AirfoilEditor")
    parser.add_argument(
        "target",
        choices=["exe", "installer", "all"],
        help="Build target to run",
    )

    args = parser.parse_args()
    repo_root = _repo_root_from_script()

    if not (repo_root / "pyproject.toml").exists():
        print(f"ERROR: pyproject.toml not found in {repo_root}")
        return 2

    try:
        if args.target == "exe":
            build_exe(repo_root, test_mode="not-slow")
        elif args.target == "installer":
            build_installer(repo_root)
        elif args.target == "all":
            build_exe(repo_root, test_mode="not-slow")
            build_installer(repo_root)
        else:
            raise RuntimeError(f"Unsupported target: {args.target}")

    except Exception as exc:
        print()
        print(f"ERROR: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
