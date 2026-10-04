"""Turns dist/EditoraPDFEdit (built by build_store.bat) into a Microsoft Store .msix package.

  python store/make_msix.py              build the package
  python store/make_msix.py --dry-run    only prepare build/msix (no Windows SDK needed)
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_APP = os.path.join(ROOT, "dist", "EditoraPDFEdit")
STAGE = os.path.join(ROOT, "build", "msix")
DRY_RUN = "--dry-run" in sys.argv


def fail(message):
    print("\nERROR:", message)
    sys.exit(1)


def app_version():
    text = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
    match = re.search(r'APP_VERSION = "(\d+\.\d+\.\d+)"', text)
    if not match:
        fail("Could not read APP_VERSION from app.py")
    return match.group(1) + ".0"          # the Store requires the 4th number to be 0


def load_config():
    with open(os.path.join(ROOT, "store", "store_config.json"), encoding="utf-8") as f:
        config = json.load(f)
    name, publisher = config["identity_name"], config["publisher"]
    if name.startswith("REPLACE") or publisher.startswith("REPLACE"):
        fail("Open store\\store_config.json and fill in the Package identity values from\n"
             "Partner Center (Product management > Product identity). See store\\README.md.")
    if not re.fullmatch(r"[A-Za-z0-9.\-]{3,50}", name):
        fail("identity_name may only contain letters, digits, '.' and '-' (3-50 characters).")
    if not publisher.startswith("CN="):
        fail("publisher must be copied exactly from Partner Center and starts with CN=")
    return config


def find_makeappx():
    roots = [os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")]
    for root in filter(None, roots):
        hits = glob.glob(os.path.join(root, "Windows Kits", "10", "bin", "*", "x64", "makeappx.exe"))
        if hits:
            return sorted(hits)[-1]
    return shutil.which("makeappx")


def main():
    config = load_config()
    version = app_version()
    if not os.path.isfile(os.path.join(DIST_APP, "EditoraPDFEdit.exe")) and not DRY_RUN:
        fail(r"dist\EditoraPDFEdit\EditoraPDFEdit.exe not found - run build_store.bat")

    if os.path.isdir(STAGE):
        shutil.rmtree(STAGE)
    if os.path.isdir(DIST_APP):
        shutil.copytree(DIST_APP, STAGE)
    else:
        os.makedirs(STAGE)
    shutil.copytree(os.path.join(ROOT, "store", "assets"), os.path.join(STAGE, "Assets"))

    manifest = open(os.path.join(ROOT, "store", "AppxManifest.xml.template"), encoding="utf-8").read()
    for token, value in {"IDENTITY_NAME": config["identity_name"], "PUBLISHER": config["publisher"],
                         "PUBLISHER_DISPLAY_NAME": config["publisher_display_name"], "VERSION": version}.items():
        manifest = manifest.replace(f"@@{token}@@", value.replace("&", "&amp;").replace('"', "&quot;"))
    with open(os.path.join(STAGE, "AppxManifest.xml"), "w", encoding="utf-8") as f:
        f.write(manifest)
    print("Package folder prepared:", STAGE)
    if DRY_RUN:
        return

    makeappx = find_makeappx()
    if not makeappx:
        fail("makeappx.exe not found. Install the Windows 10/11 SDK (it is a free download from\n"
             "Microsoft; tick 'Windows SDK Signing Tools for Desktop Apps'), then run build_store.bat again.")
    output = os.path.join(ROOT, "dist", f"EditoraPDFEdit_{version}_x64.msix")
    result = subprocess.run([makeappx, "pack", "/d", STAGE, "/p", output, "/o"])
    if result.returncode != 0:
        fail("makeappx failed - see the messages above.")
    print("\n" + "=" * 64)
    print(" Done!  Store package:", output)
    print(" Upload it in Partner Center (Packages page). See store\\README.md.")
    print("=" * 64)


if __name__ == "__main__":
    main()
