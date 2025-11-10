#!/usr/bin/env python3
"""
Backfill 'design_ver' on cad_file artifacts.

Rules:
- If data.design_ver missing/invalid -> set to (data.source_code_ver or doc.version).
- Idempotent: skips docs that already have a numeric design_ver.
- Supports --project-id filter, --dry-run, and --limit.
"""

from __future__ import annotations
from typing import Optional
from app.services.storage_gcp import C_ART, _fs  # uses your configured Firestore client

def _to_int(x) -> Optional[int]:
    try:
        return int(x)
    except Exception:
        return None

def backfill(project_id: str | None = None, dry_run: bool = False, limit: Optional[int] = None):
    q = C_ART.where("type", "==", "cad_file")
    stream = q.stream()

    batch = _fs.batch()
    scanned = 0
    updated = 0

    for snap in stream:
        scanned += 1
        d = snap.to_dict() or {}
        if project_id and d.get("projectID") != project_id:
            continue

        data = d.get("data") or {}
        current = _to_int(data.get("design_ver"))
        if current is not None:
            continue  # already good

        candidate = _to_int(data.get("source_code_ver"))
        if candidate is None:
            candidate = _to_int(d.get("version"))

        if candidate is None:
            # nothing we can infer; skip
            continue

        if dry_run:
            print(f"[DRY] would set design_ver={candidate} on {snap.id}")
        else:
            data["design_ver"] = int(candidate)
            batch.update(snap.reference, {"data": data})
            updated += 1
            if updated % 400 == 0:  # under Firestore 500-op limit
                batch.commit()
                batch = _fs.batch()

        if limit and updated >= limit:
            break

    if not dry_run and (updated % 400):
        batch.commit()

    print(f"scanned={scanned}, updated={updated}")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", help="Only backfill this project")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    backfill(project_id=args.project_id, dry_run=args.dry_run, limit=args.limit)
