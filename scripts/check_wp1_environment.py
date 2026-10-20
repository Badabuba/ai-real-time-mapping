"""Print a compact, machine-readable WP1 environment report."""

from __future__ import annotations

import json
import platform
import sys
from importlib import metadata


def package_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def main() -> None:
    report: dict[str, object] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": {
            "torch": package_version("torch"),
            "torchvision": package_version("torchvision"),
            "xformers": package_version("xformers"),
            "depth-anything-3": package_version("depth-anything-3"),
            "addict": package_version("addict"),
        },
    }

    try:
        import torch

        cuda_available = torch.cuda.is_available()
        report["cuda"] = {
            "available": cuda_available,
            "runtime": torch.version.cuda,
            "device_count": torch.cuda.device_count(),
            "device_name": torch.cuda.get_device_name(0) if cuda_available else None,
            "device_capability": (
                list(torch.cuda.get_device_capability(0)) if cuda_available else None
            ),
            "vram_gb": (
                round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2)
                if cuda_available
                else None
            ),
        }
    except Exception as exc:  # environment diagnostics must still print useful output
        report["cuda"] = {"available": False, "error": repr(exc)}

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
