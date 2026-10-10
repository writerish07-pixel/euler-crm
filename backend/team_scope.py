"""Team Leader scope — self + staff who Report to them."""
from __future__ import annotations

import re


def _norm_name(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


async def team_member_names(db, user) -> set:
    """Folded names the signed-in team lead may see: self + Reports-to staff."""
    own = _norm_name((user or {}).get("name"))
    names = {own} if own else set()
    if not own:
        return names
    rows = await db.staff.find({
        "reportsTo": {"$regex": f"^{re.escape(str((user or {}).get('name') or '').strip())}$", "$options": "i"},
        "status": {"$not": re.compile(r"^inactive$", re.I)},
    }).to_list(200)
    for row in rows:
        folded = _norm_name(row.get("name"))
        if folded:
            names.add(folded)
    return names


def lead_in_names(lead, names) -> bool:
    return _norm_name((lead or {}).get("executive")) in (names or set())


def leads_for_names(leads, names) -> list:
    return [l for l in (leads or []) if lead_in_names(l, names)]


def name_allowed_for_team_lead(executive_name, team_names) -> bool:
    return _norm_name(executive_name) in (team_names or set())
