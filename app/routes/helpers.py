# app/routes/helpers.py (new or place in routes/versions.py)
def artifact_id(art_type: str, version: int, project_id: str) -> str:
    return f"{art_type}_{version}_{project_id}"