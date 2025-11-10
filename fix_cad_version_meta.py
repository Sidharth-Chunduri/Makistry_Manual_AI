# fix_cad_version_meta.py
from __future__ import annotations
import argparse
from app.services import storage_gcp as storage
from app.services.storage_gcp import C_META

def _best_stl_for(pid: str, preferred: int | None) -> int | None:
    docs = storage.list_artifacts(pid, "cad_file", latest=False) or []
    stls = [d for d in docs if (d.get("data") or {}).get("export") == "stl"]
    if not stls:
        return None
    if preferred is not None:
        le = [d for d in stls if int(d.get("version", 0)) <= int(preferred)]
        if le:
            return int(max(le, key=lambda d: int(d.get("version", 0)))["version"])
    return int(max(stls, key=lambda d: int(d.get("version", 0)))["version"])

def _is_stl_ver(pid: str, ver: int | None) -> bool:
    if ver is None:
        return False
    doc = storage.get_artifact(pid, f"cad_file_{int(ver)}_{pid}")
    return bool(doc and (doc.get("data") or {}).get("export") == "stl")

def run(dry: bool = False):
    snaps = C_META.stream()
    patched = 0
    for s in snaps:
        meta = s.to_dict() or {}
        pid = s.id
        cad_v = meta.get("cadVersion")

        if cad_v is None:
            continue
        if _is_stl_ver(pid, cad_v):
            continue  # already valid

        new_v = _best_stl_for(pid, cad_v)
        if new_v is None or int(new_v) == int(cad_v):
            continue

        print(f"{pid}: cadVersion {cad_v} -> {new_v}")
        if not dry:
            s.reference.update({"cadVersion": int(new_v)})
            patched += 1

    print("patched:", patched)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    run(dry=args.dry)
