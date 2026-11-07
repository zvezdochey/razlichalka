# Проверка для шага 7 демо: доля заявок, где одобрение сменилось отказом, не выше порога.
# Вставляется в рабочую область «Новая проверка» целиком.
DEFAULTS = {"max_share": 0.10, "app_ids_limit": 20}


def run(mart, params=None):
    p = {**DEFAULTS, **(params or {})}
    total = mart.total_apps()
    apps = {
        s["APP_ID"] for s in mart.segments()
        if str(s["DECISION_BEFORE"]).lower() == "approve" and str(s["DECISION_AFTER"]).lower() == "reject"
    }
    share = len(apps) / total if total else 0.0
    return [{
        "LABEL": CHECK["label"],
        "SOURCE": "AFTER",
        "ARGUMENT": "approve → reject",
        "CNT": len(apps),
        "TOTAL": total,
        "METRIC": round(share, 4),
        "APP_IDS": sorted(apps)[:p["app_ids_limit"]],
        "RESULT": "FAIL" if share > p["max_share"] else "PASS",
        "CONFIDENCE": "HIGH",
    }]


CHECK = {"id": "approve_to_reject_share",
         "label": "Доля approve → reject выше 10%",
         "params": DEFAULTS,
         "entrypoint": run}
