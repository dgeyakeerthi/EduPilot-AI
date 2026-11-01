"""Deterministic eligibility, status and ranking (no LLM involved)."""
from datetime import date

def _norm(v):
    if isinstance(v, str): return v.strip().lower()
    if isinstance(v, list): return [_norm(x) for x in v]
    return v

def evaluate(c, p):
    v = p.get(c["field"])
    if v in (None, ""): return "Unknown"
    if c.get("unit") and p.get("academic_score_type") != c["unit"]: return "Unknown"  # no cross-scale compare
    v, x = _norm(v), _norm(c["value"])
    ok = {"eq": lambda: v == x, "in": lambda: v in x, "lte": lambda: v <= x, "gte": lambda: v >= x}[c["op"]]()
    return "Matched" if ok else "Unmet"

def assess(s, p):
    m, u, k, mand_unmet, mand_unknown, soft_open = [], [], [], False, False, False
    for c in s["criteria"]:
        r, mand = evaluate(c, p), c.get("mandatory", True)
        {"Matched": m, "Unmet": u, "Unknown": k}[r].append({**c, "mandatory": mand})
        if r == "Unmet" and mand: mand_unmet = True
        elif r == "Unknown" and mand: mand_unknown = True
        elif r != "Matched": soft_open = True
    st = ("not_eligible" if mand_unmet else "more_information_required" if mand_unknown
          else "possibly_eligible" if soft_open else "likely_eligible")
    return {"scholarship_id": s["scholarship_id"], "eligibility_status": st, "matched_criteria": m,
            "unmet_criteria": u, "unknown_criteria": k,
            "explanation": f"{len(m)} matched, {len(u)} unmet, {len(k)} unknown. Advisory only; not an official decision.",
            "source_references": [s["official_source_url"]]}

def status(s, today=None):
    today = today or date.today()
    o, c = s.get("opening_date"), s.get("closing_date")
    if not o or not c: return "Unknown"
    o, c = date.fromisoformat(o), date.fromisoformat(c)
    return "Upcoming" if today < o else "Open" if today <= c else "Closed"

TRUST = {"Human_Verified": 1, "Automated_Checks_Completed": .75, "Unverified": .4,
         "Conflicting_Information": 0, "Needs_Review": 0}

def rank_score(s, p, today=None):
    """Score = .40E + .25C + .15A + .10D + .10T; Provisional (no score) if any component is unavailable."""
    today = today or date.today()
    res = [(c, evaluate(c, p)) for c in s["criteria"]]
    E = sum(r == "Matched" for _, r in res) / len(res) if res else None
    def part(fields):
        rs = [r for c, r in res if c["field"] in fields]
        if not rs or "Unknown" in rs: return None
        return 1.0 if all(r == "Matched" for r in rs) else 0.0
    C, A = part({"course_name"}), part({"academic_score_value", "institution_type", "institution_name"})
    st = status(s, today)
    D = None if st == "Unknown" else 0.0 if st in ("Closed", "Suspended") else (
        0.5 if st == "Open" and (date.fromisoformat(s["closing_date"]) - today).days <= 3 else 1.0)
    T = TRUST.get(s["verification_status"])
    comps = {"E": E, "C": C, "A": A, "D": D, "T": T}
    missing = [k for k, v in comps.items() if v is None]
    if missing: return {"provisional": True, "relevance_score": None, "missing_components": missing}
    return {"provisional": False, "missing_components": [],
            "relevance_score": round(.4*E + .25*C + .15*A + .1*D + .1*T, 2)}
