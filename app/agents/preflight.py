import re

_SIMPLE_RULES = [
    (re.compile(r'\.exportStl\('),             "Remove explicit export"),
    (re.compile(r'cq\.exporters\.export\('),   "Remove explicit export"),
]

def quick_preflight(code: str) -> tuple[bool, str, str]:
    """Returns (ok, cleaned_code, msg_if_not_ok)."""
    cleaned = code
    lines = cleaned.lstrip().splitlines()
    if lines and lines[0].lstrip().startswith('.'):
        return False, cleaned, "Script missing first line before dot-chain"
    for pat, msg in _SIMPLE_RULES:
        if pat.search(cleaned):
            cleaned = pat.sub('', cleaned)
    if 'result' not in cleaned:
        return False, cleaned, "Script must assign the final object to `result`."
    return True, cleaned, ""
