"""Team Leader scope — self + staff who Report to them."""
from __future__ import annotations

import re


def _norm_name(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _email_local(value) -> str:
    local = ((value or "").split("@")[0]).replace(".", " ").replace("_", " ")
    return _norm_name(local)


def names_match(left, right) -> bool:
    """Same containment match as the executive lead book (login vs staff vs reportsTo)."""
    a, b = _norm_name(left), _norm_name(right)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def _user_aliases(user) -> list:
    """Display spellings that can identify the signed-in Team Leader."""
    raw = []
    name = str((user or {}).get("name") or "").strip()
    if name:
        raw.append(name)
    email = str((user or {}).get("email") or "").strip()
    local = _email_local(email)
    if local:
        raw.append(local)
    login = str((user or {}).get("loginId") or "").replace(".", " ").replace("_", " ").strip()
    if login:
        raw.append(login)
    seen, out = set(), []
    for item in raw:
        fold = _norm_name(item)
        if fold and fold not in seen:
            seen.add(fold)
            out.append(item)
    return out


def _staff_is_user(row, user, aliases) -> bool:
    email = _norm_name((user or {}).get("email"))
    row_email = _norm_name(row.get("email"))
    if email and "@" in email and email == row_email:
        return True
    if any(names_match(row.get("name"), alias) for alias in aliases):
        return True
    return False


def _reports_to_manager(row, manager_names, manager_ids) -> bool:
    reports = str(row.get("reportsTo") or "").strip()
    if not reports:
        return False
    if reports in manager_ids:
        return True
    return any(names_match(reports, name) for name in manager_names)


def _active_staff_rows(rows) -> list:
    out = []
    for row in rows or []:
        status = str(row.get("status") or "Active").strip()
        if status.lower() == "inactive":
            continue
        out.append(row)
    return out


async def team_member_names(db, user) -> set:
    """Folded names the signed-in team lead may see: self + Reports-to staff.

    Login name, email local-part, User ID and the matching staff-master row are
    treated as the same person, so `reportsTo: "Amit TL"` still matches a login
    named `Amit`. Lead.executive is matched later with the same fuzzy rule, so
    a staff row `Ravi Sharma` still covers leads filed as `Ravi`.
    """
    aliases = _user_aliases(user)
    names = {_norm_name(a) for a in aliases}
    if not aliases:
        return names
    rows = _active_staff_rows(await db.staff.find({}).to_list(500))
    manager_names = list(aliases)
    manager_ids = set()
    for row in rows:
        if not _staff_is_user(row, user, aliases):
            continue
        staff_name = str(row.get("name") or "").strip()
        if staff_name:
            manager_names.append(staff_name)
            names.add(_norm_name(staff_name))
        staff_id = str(row.get("staffId") or "").strip()
        if staff_id:
            manager_ids.add(staff_id)
    for row in rows:
        if not _reports_to_manager(row, manager_names, manager_ids):
            continue
        folded = _norm_name(row.get("name"))
        if folded:
            names.add(folded)
        local = _email_local(row.get("email"))
        if local:
            names.add(local)
    return names


def lead_in_names(lead, names) -> bool:
    return name_allowed_for_team_lead((lead or {}).get("executive"), names)


def leads_for_names(leads, names) -> list:
    return [l for l in (leads or []) if lead_in_names(l, names)]


def name_allowed_for_team_lead(executive_name, team_names) -> bool:
    ex = _norm_name(executive_name)
    if not ex:
        return False
    for name in (team_names or set()):
        if names_match(ex, name):
            return True
    return False
