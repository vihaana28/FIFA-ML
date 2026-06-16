from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: str | Path = ".env") -> int:
    env_path = Path(path)
    if not env_path.exists():
        return 0

    loaded = 0
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")
        loaded += 1
    return loaded
