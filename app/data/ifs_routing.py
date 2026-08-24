"""IFS routing discovery for the add-program onboarding flow.

Pulls a part's operation routing from ROUTING_OPERATION_CFV (verified: returns OPERATION_NO,
WORK_CENTER_NO, OPERATION_DESCRIPTION) so a new program's ops list can be prefilled instead of
hand-typed. Also flags work centers the engine's crew/shift-budget tables don't know about —
an unknown WC silently gets DEFAULT_SHIFT and produces plausible-but-wrong dates, so the admin
flow BLOCKS save until the PM defines the WC or maps it to a known one.
"""

SQL_ROUTING = """
SELECT r.OPERATION_NO AS OPNO, r.WORK_CENTER_NO AS WC,
       r.OPERATION_DESCRIPTION AS DESCR
FROM ROUTING_OPERATION_CFV r
WHERE r.PART_NO = '{part}'
ORDER BY r.OPERATION_NO
"""


def known_wcs() -> set:
    """Work centers the capacity engine has an explicit shift/crew budget for (from routers.WC_SHIFT).
    Anything outside this set falls back to DEFAULT_SHIFT — the silent-wrong-budget risk."""
    import routers as R
    return {wc for (_prog, wc) in R.WC_SHIFT.keys()}


def discover_routing(client, part_no: str) -> list[dict]:
    """Blocking IFS pull of a part's routing. Returns [{opno, wc, desc}] sorted by opno.
    `client` is an authenticated IfsMcpClient (caller runs this in a thread)."""
    res = client.execute_query(SQL_ROUTING.format(part=part_no))
    rows = res.get("data", []) if isinstance(res, dict) else (res or [])
    out = []
    for r in rows:
        try:
            opno = int(r["OPNO"])
        except (TypeError, ValueError):
            continue
        out.append(dict(opno=opno, wc=(r.get("WC") or "").strip(),
                        desc=(r.get("DESCR") or "").strip()))
    out.sort(key=lambda o: o["opno"])
    return out


def unknown_wcs(routing: list[dict]) -> list[str]:
    """WCs in the routing that the engine has no budget for (need PM action before save)."""
    known = known_wcs()
    seen, unknown = set(), []
    for op in routing:
        wc = op.get("wc")
        if wc and wc not in known and wc not in seen:
            seen.add(wc)
            unknown.append(wc)
    return unknown
