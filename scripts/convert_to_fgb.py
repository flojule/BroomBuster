#!/usr/bin/env python3
"""
Pre-build FlatGeobuf files for all cities.

Run this once (or after updating raw data files) to produce the fast-load
.fgb files consumed at runtime by data_loader.load_city_data().

Usage (from repo root):
    python scripts/convert_to_fgb.py [city_key ...]

    # Convert all cities:
    python scripts/convert_to_fgb.py

    # Force-rebuild one city:
    python scripts/convert_to_fgb.py san_francisco --force

Options:
    --force   Delete existing FGB files and rebuild from raw source.
              For auto-download cities (SF, Chicago) this also re-downloads
              the raw data.
"""

import os
import sys
import time
import argparse

# Allow importing from src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import data_loader
from cities import CITIES

_ROOT = os.path.join(os.path.dirname(__file__), "..")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cities", nargs="*", help="City keys to convert (default: all)")
    ap.add_argument("--force", action="store_true",
                    help="Delete existing FGB and rebuild from scratch")
    args = ap.parse_args()

    keys = args.cities or list(CITIES.keys())
    unknown = [k for k in keys if k not in CITIES]
    if unknown:
        ap.error(f"Unknown city key(s): {', '.join(unknown)}\n"
                 f"Valid keys: {', '.join(CITIES)}")

    print(f"Converting {len(keys)} city/cities to FlatGeobuf …\n")
    total_t = 0.0

    for key in keys:
        city = CITIES[key]
        fgb_rel = city.get("fgb_path", "")
        fgb_abs = os.path.join(_ROOT, fgb_rel) if fgb_rel else None

        if fgb_abs and os.path.exists(fgb_abs) and not args.force:
            sz = os.path.getsize(fgb_abs) / 1_048_576
            print(f"  {city['name']:30s}  already built  ({sz:.1f} MB)  — skip  "
                  f"(use --force to rebuild)")
            continue

        print(f"  {city['name']} …")
        t0 = time.time()
        try:
            gdf = data_loader.load_city_data(key, force_refresh=args.force)
            elapsed = time.time() - t0
            total_t += elapsed
            print(f"    {len(gdf):,} rows  {elapsed:.1f}s")
        except FileNotFoundError as exc:
            print(f"    SKIP — {exc}")
        except Exception as exc:
            print(f"    ERROR — {exc}")

    print(f"\nDone.  Total time: {total_t:.1f}s")


if __name__ == "__main__":
    main()
