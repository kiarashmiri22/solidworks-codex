from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys


def diagnose() -> dict[str, dict[str, str | bool]]:
    results: dict[str, dict[str, str | bool]] = {}
    is_windows = os.name == "nt"
    results["windows"] = {
        "ok": is_windows,
        "detail": "Windows is required for SolidWorks COM automation." if not is_windows else "Windows detected.",
    }
    py_ok = sys.version_info >= (3, 11)
    results["python"] = {
        "ok": py_ok,
        "detail": f"Python {sys.version_info.major}.{sys.version_info.minor}" + (" detected." if py_ok else "; Python 3.11+ is required."),
    }
    for module, label in (("mcp", "MCP Python SDK"), ("win32com", "pywin32")):
        present = importlib.util.find_spec(module) is not None
        results[module] = {
            "ok": present,
            "detail": f"{label} is installed." if present else f"{label} is missing; run scripts/install.ps1.",
        }

    com_registered = False
    detail = "SolidWorks COM registration could not be checked outside Windows."
    if is_windows:
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "SldWorks.Application"):
                pass
            com_registered = True
            detail = "SldWorks.Application is registered in Windows."
        except OSError:
            detail = "SldWorks.Application is not registered; repair or install SolidWorks."
    results["solidworks_com"] = {"ok": com_registered, "detail": detail}
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local prerequisites without launching SolidWorks.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero if a prerequisite is missing.")
    args = parser.parse_args()
    results = diagnose()
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for name, result in results.items():
            mark = "OK" if result["ok"] else "MISSING"
            print(f"[{mark}] {name}: {result['detail']}")
    return int(args.strict and not all(bool(result["ok"]) for result in results.values()))


if __name__ == "__main__":
    raise SystemExit(main())
