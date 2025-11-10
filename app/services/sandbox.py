"""
Lightweight sandbox for Makistry.
Runs un-trusted CADQuery code in a forked Python process with
  •  wall-clock timeout
  •  memory limit (POSIX only)
  •  clean temp directory

Returns a STEP file path on success or raises SandboxError on failure.
"""

from __future__ import annotations

import os, subprocess, tempfile, textwrap, uuid, shutil, sys, resource
from pathlib import Path
TIME_LIMIT = 180          # seconds
MEM_LIMIT_MB = 2048       # address-space cap (soft+hard)

class SandboxError(RuntimeError):
    """Raised when user CADQuery code fails or times out."""

def _run_child(script_path: str) -> subprocess.CompletedProcess:
    """Launch a child Python interpreter with optional RLIMIT caps."""
    def _set_limits() -> None:
        try:
            # RLIMIT_AS not available on macOS; fall back to data segment.
            limit_name = getattr(resource, "RLIMIT_AS", resource.RLIMIT_DATA)
            resource.setrlimit(
                limit_name,
                (MEM_LIMIT_MB * 2**20, MEM_LIMIT_MB * 2**20),
            )
        except (ValueError, OSError, AttributeError):
            # Platform does not support this limit; continue without it.
            pass

    return subprocess.run(
        [sys.executable, script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=TIME_LIMIT,
        preexec_fn=_set_limits if os.name == "posix" else None,
    )

def run_cadquery(code: str, ext: str = "stl") -> str:
    """
    Execute CADQuery code and return a file path.
    (`export_ext` = "stl" | "step").
    Raises SandboxError on timeout or failure.
    """
    with tempfile.TemporaryDirectory(prefix="cqrun_") as tmp:
        script_path = os.path.join(tmp, "model_script.py")
        geom_path   = os.path.join(tmp, f"model.{ext}")

        # trailer = textwrap.dedent(f"""
        #     import cadquery as cq, sys

        #     obj = locals().get("result") or (locals().get("build") and locals()["build"]())
        #     if obj is None:
        #         raise RuntimeError("Script must define build() or result = Workplane/Assembly")
                                  
        #     # Allow both Workplane and Assembly
        #     def _final_shape(o):
        #         # Assembly → Compound (Shape)
        #         if isinstance(o, cq.Assembly):
        #             return o.toCompound()
        #         # Workplane → single Solid
        #         if isinstance(o, cq.Workplane):
        #             solids = o.solids()
        #             if solids.size() == 0:
        #                 raise RuntimeError("No solids found in Workplane.")
        #             if solids.size() > 1:
        #                 o = o.combineSolids()
        #                 solids = o.solids()
        #             return solids.val()
        #         # Already a Shape/Solid/Compound
        #         if hasattr(o, "isValid"):
        #             return o
        #         raise RuntimeError(f"Unsupported result type: {{type(o)}}")

        #     shape = _final_shape(obj)
       
        #     if not shape or not shape.isValid():
        #         raise RuntimeError("Final shape is null or invalid.")
            
        #     cq.exporters.export(shape, r"{stl_path}")
        # """)
        trailer = textwrap.dedent(f"""
            import cadquery as cq, sys

            obj = locals().get("result") or (locals().get("build") and locals()["build"]())

            # -------- accept Assembly or Workplane --------------------------
            def _final_shape(o):
                # Assembly  → single Compound
                if isinstance(o, cq.Assembly):
                    return o.toCompound()
                # Workplane → single Solid
                if isinstance(o, cq.Workplane):
                    solids = o.solids()
                    if solids.size() > 1:
                        o = o.combineSolids()
                        solids = o.solids()
                    return solids.val()
                # Already a Shape / Solid / Compound
                if hasattr(o, "isValid"):
                    return o
                raise RuntimeError(f"Unsupported result type")

            is_step = "{ext}".lower() in ("step","stp")
            out_path = r"{geom_path}"

            if is_step and isinstance(obj, cq.Assembly):
                # Export assembly directly for STEP (faster than toCompound for big trees)
                cq.exporters.export(obj, out_path, exportType="STEP")
            else:
                shape = _final_shape(obj)
                if not shape or not shape.isValid():
                    raise RuntimeError("Final shape is null or invalid")
                cq.exporters.export(
                    shape,
                    out_path,
                    exportType=("STEP" if is_step else None),
                )
        """)

        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code.rstrip() + "\n\n" + trailer)

        try:
            proc = _run_child(script_path)
        except subprocess.TimeoutExpired:
            raise SandboxError(f"Execution exceeded {TIME_LIMIT}s")

        if proc.returncode != 0:
            raise SandboxError(proc.stderr or proc.stdout or "Unknown error")
        # Create temp directory for output files if it doesn't exist
        temp_dir = os.path.join(os.getcwd(), "temp", "geometry")
        os.makedirs(temp_dir, exist_ok=True)
        
        final = os.path.join(temp_dir, f"{uuid.uuid4()}.{ext}")
        shutil.copy(geom_path, final)
        return final