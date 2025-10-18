"""Quick helper to verify Amazon Product Advertising API credentials.

Usage (from project root):
    python -m operations_dashboard.verify_amazon_keys --asin B0BP9F9DSF --marketplace US

When executed as a standalone script via ``python operations_dashboard/verify_amazon_keys.py``,
it automatically adds the project root to ``sys.path`` so that imports work.

Environment variables expected (same as the main app):
    AMAZON_ACCESS_KEY
    AMAZON_SECRET_KEY
    AMAZON_ASSOCIATE_TAG
    AMAZON_MARKETPLACE (optional, defaults to US)

If the call succeeds the script prints the first item's title.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

if __package__ in {None, ""}:
    # Ensure project root is importable when executed as a file.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from operations_dashboard.config import AmazonCredentialConfig

try:
    from amazon_paapi import AmazonApi
except ImportError as exc:  # pragma: no cover - helpful message for manual runs
    raise RuntimeError(
        "Missing dependency 'python-amazon-paapi'. "
        "Install it with `pip install python-amazon-paapi` before running this script."
    ) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Amazon PAAPI credentials.")
    parser.add_argument(
        "--asin",
        default="B0BP9F9DSF",
        help="ASIN to fetch for a simple verification call (default: %(default)s).",
    )
    parser.add_argument(
        "--marketplace",
        default=None,
        help="Override marketplace (e.g. US, UK). Falls back to AMAZON_MARKETPLACE.",
    )
    args = parser.parse_args(argv)

    try:
        conf = AmazonCredentialConfig.from_env()
    except RuntimeError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    marketplace = args.marketplace or conf.marketplace
    client = AmazonApi(
        conf.access_key,
        conf.secret_key,
        conf.associate_tag or "",
        marketplace,
    )

    print(
        f"[info] Testing credentials for marketplace={marketplace} "
        f"associate_tag={conf.associate_tag or '(empty)'}"
    )

    try:
        response = client.get_items([args.asin])
    except Exception as exc:  # pragma: no cover - external dependency
        print(f"[error] Request failed: {exc}", file=sys.stderr)
        return 2

    items = getattr(response, "items", []) or []
    if not items:
        print("[warn] Request succeeded but returned no items. Check ASIN or permissions.")
        return 3

    first = items[0]
    title = getattr(getattr(first, "item_info", None), "title", None)
    if title and hasattr(title, "display_value"):
        readable_title = title.display_value
    else:
        readable_title = getattr(first, "asin", "(unknown ASIN)")

    print(f"[ok] Credentials are valid. Sample item title: {readable_title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
