from __future__ import annotations

import argparse
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docs" / "templates" / "work-card.yaml"
DEFAULT_TARGET = ROOT / "experiments" / "spikes" / "current-work.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an ignored work-card for one focused agent session")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--force", action="store_true", help="Replace an existing card")
    args = parser.parse_args()
    target = args.target if args.target.is_absolute() else ROOT / args.target
    if target.exists() and not args.force:
        raise SystemExit(f"Work-card already exists: {target}. Use --force to replace it.")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TEMPLATE, target)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
