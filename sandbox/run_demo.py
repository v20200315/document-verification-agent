from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

# Running this file directly places sandbox/, not the repository root, on sys.path.
SANDBOX_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SANDBOX_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Prefer explicitly exported values, then fill missing settings from .env.
load_dotenv(PROJECT_ROOT / ".env", override=False)

from sandbox.src.errors import DocumentPipelineError
from sandbox.src.pipeline import DocumentPipeline


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract and classify a document with Qwen."
    )
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        default=SANDBOX_DIR / "uploads" / "temp01.jpg",
        help="PDF or JPG/JPEG/PNG path (defaults to uploads/temp01.jpg).",
    )
    args = parser.parse_args()

    try:
        pipeline = DocumentPipeline.from_env()
        result = pipeline.run(args.file)
    except DocumentPipelineError as exc:
        print(f"Document pipeline error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(
            f"Unexpected document pipeline error: {exc.__class__.__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    print(result.model_dump_json(indent=2, exclude_none=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
