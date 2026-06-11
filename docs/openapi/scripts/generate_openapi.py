"""Generate and persist OpenAPI artifacts for Flowcept webservice."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from flowcept.webservice.main import app


def main() -> None:
    outdir = Path("docs/openapi")
    outdir.mkdir(parents=True, exist_ok=True)

    openapi_schema = app.openapi()

    json_path = outdir / "flowcept-openapi.json"
    json_path.write_text(json.dumps(openapi_schema, indent=2), encoding="utf-8")

    yaml_path = outdir / "flowcept-openapi.yaml"
    try:
        import yaml
    except Exception:
        yaml_path.write_text(
            "# Install pyyaml to generate YAML from the OpenAPI JSON artifact.\n",
            encoding="utf-8",
        )
    else:
        yaml_path.write_text(yaml.safe_dump(openapi_schema, sort_keys=False), encoding="utf-8")


if __name__ == "__main__":
    main()
