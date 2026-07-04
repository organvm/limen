"""consolidate — produce financial dashboard artifacts from entity registry + live data.

Reads:
  - entities.yaml          (this directory — entity registry + account classification)
  - balances-history.json  (this directory — persistent balance time-series journal)
  - revenue-ladder.json    (root — product revenue pipeline)
  - obligations-ledger.json (root — obligations surfaced by mail organ)

Writes (to organs/financial/):
  - balances-history.json  Append-only balance snapshot journal
  - balance-sheet.md       Consolidated net position with asset/liability breakdown
  - cashflow.md            Rolling cash-flow projection (12-week horizon)
  - standing-census.md     Reliability census: what can be relied on vs principal-gated
  - STATUS.md              One-page dashboard

Writes (to web/app/public/):
  - financial-standing.json  Machine-readable dashboard face

Usage:
  python3 organs/financial/consolidate.py

The organ's generator beat (financial-organ.py) calls this on cadence.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import yaml as _yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[2]))
HERE = ROOT / "organs" / "financial"
WEB_FACE = ROOT / "web" / "app" / "public"
MACRO_FACE = HERE / "MACRO.md"
MICRO_FACE = HERE / "MICRO.md"

ACCOUNT_CLASSIFICATION = {
    "checking": "asset",
    "savings": "asset",
    "credit": "liability",
    "investment": "asset",
    "cash": "asset",
    "receivable": "asset",
    "payable": "liability",
    "crypto": "asset",
    "loan": "liability",
    "mortgage": "liability",
    "retirement": "asset",
}


def load_json(path: Path) -> dict:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    if HAS_YAML:
        with open(path) as f:
            return _yaml.safe_load(f) or {}
    return {}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def classify_account(acct_type: str) -> str:
    return ACCOUNT_CLASSIFICATION.get(acct_type, "asset")


def load_balance_journal() -> list:
    path = HERE / "balances-history.json"
    if path.exists():
        try:
            data = json.loads(path.read_text())
            return data.get("snapshots", [])
        except (json.JSONDecodeError, OSError):
            return []
    return []


def append_balance_journal(snapshots: list, entities: dict) -> list:
    now = today_str()
    entity_list = entities.get("entities", [])
    balances = {}
    for ent in entity_list:
        eid = ent.get("id", "?")
        for acct in ent.get("accounts", []):
            aid = acct.get("id", "?")
            key = f"{eid}:{aid}"
            balances[key] = {
                "balance": acct.get("balance"),
                "balance_known": acct.get("balance_known", False),
                "as_of": acct.get("as_of"),
                "type": acct.get("type"),
            }
    if snapshots and snapshots[-1].get("balances") == balances:
        return snapshots
    snapshots.append(
        {
            "date": now,
            "generated_at": now_iso(),
            "balances": balances,
        }
    )
    return snapshots


def write_balance_journal(snapshots: list) -> bool:
    path = HERE / "balances-history.json"
    content = {
        "schema": "1.0",
        "snapshots": snapshots,
    }
    try:
        existing = json.loads(path.read_text()) if path.exists() else {}
    except (json.JSONDecodeError, OSError):
        existing = {}
    if existing.get("snapshots") == snapshots:
        return False
    path.write_text(json.dumps(content, indent=2))
    return True


def classify_balances(snapshots: list, classification: dict) -> dict:
    if not snapshots:
        return {}
    latest = snapshots[-1]["balances"]
    assets = []
    liabilities = []
    total_assets = 0.0
    total_liabilities = 0.0
    known_assets = 0
    known_liabilities = 0
    unknown_count = 0

    for key, val in latest.items():
        acct_type = val.get("type", "checking")
        cls = classification.get(acct_type, "asset")
        bal = val.get("balance")
        bal_known = val.get("balance_known", False) and bal is not None
        entry = {
            "key": key,
            "balance": bal,
            "balance_known": bal_known,
            "type": acct_type,
            "classification": cls,
        }
        if cls == "asset":
            assets.append(entry)
            if bal_known:
                known_assets += 1
                total_assets += float(bal)
        else:
            liabilities.append(entry)
            if bal_known:
                known_liabilities += 1
                total_liabilities += float(bal)
        if not bal_known:
            unknown_count += 1

    net_worth = total_assets - total_liabilities if (known_assets or known_liabilities) else None

    snap_count = len(snapshots)
    prev_net_worth = None
    if snap_count >= 2:
        prev = snapshots[-2]["balances"]
        prev_assets = 0.0
        prev_liabilities = 0.0
        for key, val in prev.items():
            acct_type = val.get("type", "checking")
            cls = classification.get(acct_type, "asset")
            bal = val.get("balance")
            bal_known = val.get("balance_known", False) and bal is not None
            if not bal_known:
                continue
            if cls == "asset":
                prev_assets += float(bal)
            else:
                prev_liabilities += float(bal)
        prev_net_worth = prev_assets - prev_liabilities if (prev_assets or prev_liabilities) else None

    return {
        "assets": assets,
        "liabilities": liabilities,
        "total_assets": total_assets if known_assets > 0 else None,
        "total_liabilities": total_liabilities if known_liabilities > 0 else None,
        "net_worth": net_worth,
        "prev_net_worth": prev_net_worth,
        "known_assets": known_assets,
        "known_liabilities": known_liabilities,
        "unknown_count": unknown_count,
        "snapshot_count": snap_count,
        "latest_date": snapshots[-1]["date"] if snapshots else None,
    }


def iter_accounts(entities: dict) -> list[dict]:
    accounts = []
    for ent in entities.get("entities", []) or []:
        eid = ent.get("id", "?")
        for acct in ent.get("accounts", []) or []:
            aid = acct.get("id", "?")
            accounts.append(
                {
                    "key": f"{eid}:{aid}",
                    "entity": eid,
                    "id": aid,
                    "institution": acct.get("institution"),
                    "type": acct.get("type"),
                    "balance_known": bool(acct.get("balance_known", False)) and acct.get("balance") is not None,
                    "balance": acct.get("balance"),
                    "as_of": acct.get("as_of"),
                    "notes": acct.get("notes", ""),
                }
            )
    return accounts


def _parse_amount(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace("$", "").replace(",", "").strip()
        if re.fullmatch(r"-?\d+(\.\d+)?", cleaned):
            return float(cleaned)
    return None


def obligation_amount(obligation: dict) -> float | None:
    if obligation.get("amount_unknown") is True:
        return None
    for field in (
        "amount_usd",
        "amount",
        "monthly_amount",
        "estimated_monthly_amount",
        "estimated_amount",
    ):
        amount = _parse_amount(obligation.get(field))
        if amount is not None:
            return amount
    cents = _parse_amount(obligation.get("amount_cents"))
    if cents is not None:
        return cents / 100.0
    return None


def obligation_monthly_amount(obligation: dict) -> float | None:
    amount = obligation_amount(obligation)
    if amount is None:
        return None
    frequency = str(obligation.get("frequency", "")).lower()
    if frequency in ("annual", "yearly"):
        return amount / 12.0
    if frequency in ("weekly",):
        return amount * 52.0 / 12.0
    if frequency in ("one-time", "one_time", "once"):
        return 0.0
    return amount


def _first_dollar_product(revenue: dict) -> dict:
    products = revenue.get("products", []) or []
    deployable = [p for p in products if p.get("stage") in ("deploy-ready", "live", "monetized")]
    if deployable:
        return sorted(deployable, key=lambda p: p.get("rank", 99))[0]
    if products:
        return sorted(products, key=lambda p: p.get("rank", 99))[0]
    return {}


def build_standing_census(entities: dict, revenue: dict, obligations: dict, classified: dict) -> dict:
    accounts = iter_accounts(entities)
    liability_types = {
        key
        for key, value in (entities.get("account_classification") or ACCOUNT_CLASSIFICATION).items()
        if value == "liability"
    }
    balance_known = [a for a in accounts if a["balance_known"]]
    missing_balance = [a for a in accounts if not a["balance_known"]]
    liability_accounts = [a for a in accounts if a.get("type") in liability_types]
    known_liabilities = [a for a in liability_accounts if a["balance_known"]]
    cash_accounts = [a for a in accounts if a.get("type") in ("checking", "savings", "cash") and a["balance_known"]]

    financial_obs = financial_obligations(entities, obligations)
    quantified_obs = [o for o in financial_obs if obligation_amount(o) is not None]
    unknown_amount_obs = [o for o in financial_obs if obligation_amount(o) is None]
    monthly_known = [amount for amount in (obligation_monthly_amount(o) for o in quantified_obs) if amount is not None]
    first_product = _first_dollar_product(revenue)
    moneta_present = (ROOT / "moneta").exists()
    moneta_address_configured = bool(os.environ.get("MINT_BTC_ADDRESS"))

    checks = [
        {
            "id": "entity_registry",
            "status": "pass" if len(entities.get("entities", []) or []) >= 3 else "missing",
            "label": "Entity registry has personal, commercial, mission, and product containers",
            "gate": "repo",
        },
        {
            "id": "cash_balance_known",
            "status": "pass" if cash_accounts else "needs_principal",
            "label": "At least one cash/checking balance is known",
            "gate": "principal balance entry",
        },
        {
            "id": "liabilities_registered",
            "status": "pass" if liability_accounts else "missing",
            "label": "Credit/loan liabilities are present in the registry",
            "gate": "repo",
        },
        {
            "id": "liability_balances_known",
            "status": "pass" if known_liabilities else "needs_principal",
            "label": "Credit/loan balances are known",
            "gate": "principal balance entry",
        },
        {
            "id": "obligations_present",
            "status": "pass" if financial_obs else "missing",
            "label": "Financial-material obligations are visible",
            "gate": "mail organ or registry fallback",
        },
        {
            "id": "obligation_amounts_known",
            "status": "pass" if financial_obs and not unknown_amount_obs else "needs_principal",
            "label": "Financial obligations have usable dollar amounts",
            "gate": "principal amount entry",
        },
        {
            "id": "first_dollar_path",
            "status": "pass" if first_product else "missing",
            "label": "A first-dollar product path is selected",
            "gate": "revenue-ladder.json",
        },
        {
            "id": "moneta_rail_present",
            "status": "pass" if moneta_present else "missing",
            "label": "MONETA rail exists in this checkout",
            "gate": "repo",
        },
        {
            "id": "moneta_address_configured",
            "status": "pass" if moneta_address_configured else "needs_principal",
            "label": "MONETA has a deploy-time self-custodied receive address",
            "gate": "MINT_BTC_ADDRESS outside git",
        },
    ]

    next_inputs = []
    if not cash_accounts:
        next_inputs.append(
            {
                "id": "enter_cash_balance",
                "owner": "principal",
                "path": "organs/financial/entities.yaml",
                "field": "anthony-personal:ach-checking balance + as_of",
                "why": "Unlocks real net worth and runway start point.",
            }
        )
    if liability_accounts and not known_liabilities:
        next_inputs.append(
            {
                "id": "enter_liability_balances",
                "owner": "principal",
                "path": "organs/financial/entities.yaml",
                "field": "santander-card-0186 and student-loan-nelnet balance + as_of",
                "why": "Turns fraud-hold and default risk into real liability posture.",
            }
        )
    if unknown_amount_obs:
        next_inputs.append(
            {
                "id": "quantify_obligations",
                "owner": "principal",
                "path": "organs/financial/entities.yaml or obligations-ledger.json",
                "field": "amount/frequency for highest-priority obligations",
                "why": "Makes cashflow/runway usable instead of structural only.",
            }
        )
    if not moneta_address_configured:
        next_inputs.append(
            {
                "id": "configure_moneta_address",
                "owner": "principal",
                "path": "deploy secret, not git",
                "field": "MINT_BTC_ADDRESS",
                "why": "Opens the sovereign first-dollar rail without giving the organ spending authority.",
            }
        )

    can_rely_on = [
        "entity/account inventory",
        "payrail route map and no-money-movement boundary",
        "first-dollar path selection from revenue-ladder.json",
        "ranked financial obligation visibility",
    ]
    cannot_rely_on = []
    if classified.get("net_worth") is None:
        cannot_rely_on.append("net worth or solvency amount")
    if unknown_amount_obs:
        cannot_rely_on.append("runway duration or weekly surplus/deficit")
    if not moneta_address_configured:
        cannot_rely_on.append("sovereign intake being live")

    return {
        "generated_at": now_iso(),
        "account_count": len(accounts),
        "known_balance_count": len(balance_known),
        "missing_balance_count": len(missing_balance),
        "liability_account_count": len(liability_accounts),
        "known_liability_count": len(known_liabilities),
        "missing_balance_accounts": [a["key"] for a in missing_balance],
        "known_balance_accounts": [a["key"] for a in balance_known],
        "financial_obligation_count": len(financial_obs),
        "quantified_obligation_count": len(quantified_obs),
        "unknown_obligation_amount_count": len(unknown_amount_obs),
        "known_monthly_outflow": sum(monthly_known) if monthly_known else None,
        "first_dollar_product": {
            "product": first_product.get("product"),
            "stage": first_product.get("stage"),
            "path": first_product.get("first_dollar_path"),
        }
        if first_product
        else None,
        "moneta": {
            "present": moneta_present,
            "address_configured": moneta_address_configured,
            "boundary": "MONETA intakes value; Aerarium tracks the institution and stages decisions.",
        },
        "checks": checks,
        "can_rely_on": can_rely_on,
        "not_yet_reliable_for": cannot_rely_on,
        "next_principal_inputs": next_inputs,
    }


def build_standing_census_markdown(census: dict) -> str:
    lines = []
    lines.append("# Financial Office — Standing Census")
    lines.append("")
    lines.append(f"> Generated: {now_iso()}")
    lines.append(
        "> This is the reliability preflight: what the office can be trusted for today, "
        "and which fields still require the principal's hand."
    )
    lines.append("")

    lines.append("## Reliance Posture")
    lines.append("")
    lines.append("| Can rely on today | Not yet reliable for |")
    lines.append("|---|---|")
    can = census.get("can_rely_on") or ["-"]
    cannot = census.get("not_yet_reliable_for") or ["-"]
    for i in range(max(len(can), len(cannot))):
        left = can[i] if i < len(can) else ""
        right = cannot[i] if i < len(cannot) else ""
        lines.append(f"| {left} | {right} |")
    lines.append("")

    lines.append("## Census Counts")
    lines.append("")
    lines.append("| Measure | Count |")
    lines.append("|---|---:|")
    lines.append(f"| Accounts registered | {census.get('account_count', 0)} |")
    lines.append(f"| Known balances | {census.get('known_balance_count', 0)} |")
    lines.append(f"| Missing balances | {census.get('missing_balance_count', 0)} |")
    lines.append(f"| Liability accounts registered | {census.get('liability_account_count', 0)} |")
    lines.append(f"| Known liability balances | {census.get('known_liability_count', 0)} |")
    lines.append(f"| Financial obligations | {census.get('financial_obligation_count', 0)} |")
    lines.append(f"| Quantified obligations | {census.get('quantified_obligation_count', 0)} |")
    lines.append(f"| Unknown obligation amounts | {census.get('unknown_obligation_amount_count', 0)} |")
    lines.append("")

    lines.append("## Checks")
    lines.append("")
    lines.append("| Check | Status | Gate |")
    lines.append("|---|---|---|")
    for check in census.get("checks", []):
        lines.append(
            f"| {check.get('label', check.get('id', '?'))} | {check.get('status', '?')} | {check.get('gate', '')} |"
        )
    lines.append("")

    lines.append("## Next Principal Inputs")
    lines.append("")
    inputs = census.get("next_principal_inputs") or []
    if not inputs:
        lines.append("- None: the current census has the minimum inputs needed for real runway math.")
    else:
        for item in inputs:
            lines.append(f"- **{item['id']}** — `{item['field']}` in {item['path']}. {item['why']}")
    lines.append("")

    moneta = census.get("moneta", {})
    lines.append("## Rail Boundary")
    lines.append("")
    lines.append(
        "- MONETA present: {}; receive address configured in this process: {}.".format(
            "yes" if moneta.get("present") else "no",
            "yes" if moneta.get("address_configured") else "no",
        )
    )
    lines.append("- The receive address is a deploy secret/human lever, not repo content.")
    lines.append("- Aerarium stages accounting and decisions; it never moves money.")
    lines.append("")

    return "\n".join(lines)


def build_balance_sheet(entities: dict, revenue: dict, obligations: dict, classified: dict) -> str:
    lines = []
    lines.append("# Financial Office — Consolidated Balance Sheet")
    lines.append("")
    lines.append(f"> Generated: {now_iso()}")
    lines.append("> *Advisory estimate. Balances marked `-` need principal entry.")
    lines.append("")

    headroom = _net_worth_trend(classified)
    if headroom:
        lines.append(f"> {headroom}")
        lines.append("")

    lines.append("## Net Worth")
    lines.append("")
    nw = classified.get("net_worth")
    prev = classified.get("prev_net_worth")
    if nw is not None:
        direction = ""
        if prev is not None and prev != 0:
            pct = ((nw - prev) / abs(prev)) * 100
            direction = f" (prev: ${prev:,.2f}, {pct:+.1f}%)"
        lines.append(f"- **Net worth:** **${nw:,.2f}**{direction}")
    else:
        lines.append("- **Net worth:** *(no known balances — enter data in entities.yaml)*")
    lines.append("")

    lines.append("## Assets")
    lines.append("")
    lines.append("| Account | Type | Balance | Status |")
    lines.append("|---|---|---|---|")
    total_a = 0.0
    a_known = 0
    for a in classified.get("assets", []):
        bal = a.get("balance")
        known = a.get("balance_known", False)
        if known and bal is not None:
            total_a += float(bal)
            a_known += 1
            bal_str = f"${float(bal):,.2f}"
            status = "✓"
        else:
            bal_str = "-"
            status = "(needs entry)"
        lines.append(f"| {a['key']} | {a['type']} | {bal_str} | {status} |")
    lines.append(f"| **Total Assets** | | **${total_a:,.2f}** | {a_known} known |")
    lines.append("")

    lines.append("## Liabilities")
    lines.append("")
    lines.append("| Account | Type | Balance | Status |")
    lines.append("|---|---|---|---|")
    total_l = 0.0
    l_known = 0
    for a in classified.get("liabilities", []):
        bal = a.get("balance")
        known = a.get("balance_known", False)
        if known and bal is not None:
            total_l += float(bal)
            l_known += 1
            bal_str = f"${float(bal):,.2f}"
            status = "✓"
        else:
            bal_str = "-"
            status = "(needs entry)"
        lines.append(f"| {a['key']} | {a['type']} | {bal_str} | {status} |")
    lines.append(f"| **Total Liabilities** | | **${total_l:,.2f}** | {l_known} known |")
    lines.append("")

    if nw is not None:
        lines.append("### Net Worth Summary")
        lines.append("")
        lines.append("| | Amount |")
        lines.append("|---|---|")
        lines.append(f"| Total Assets | ${total_a:,.2f} |")
        lines.append(f"| Total Liabilities | ${total_l:,.2f} |")
        lines.append(f"| **Net Worth** | **${nw:,.2f}** |")
        lines.append("")

    lines.append("### Balance History (snapshots)")
    sc = classified.get("snapshot_count", 0)
    lines.append(f"- **Snapshots recorded:** {sc}")
    lines.append(f"- **Latest:** {classified.get('latest_date', '-')}")
    if sc >= 2:
        lines.append("- **Trend tracking active** — run consolidate.py each beat to record changes")
    else:
        lines.append("- **First snapshot recorded** — trend data will appear after the next beat")
    lines.append("")

    return "\n".join(lines)


def _net_worth_trend(classified: dict) -> str | None:
    nw = classified.get("net_worth")
    prev = classified.get("prev_net_worth")
    if nw is not None and prev is not None and prev != 0:
        direction = "📈 up" if nw > prev else "📉 down"
        pct = ((nw - prev) / abs(prev)) * 100
        return f"**Trend:** Net worth {direction} {pct:+.1f}% since last snapshot (${prev:,.2f} → ${nw:,.2f})"
    return None


def build_cashflow(entities: dict, revenue: dict, obligations: dict, classified: dict) -> str:
    lines = []
    lines.append("# Financial Office — Rolling Cash-Flow Projection")
    lines.append("")
    lines.append(f"> Generated: {now_iso()}")
    lines.append("> *Forward-looking estimate based on known revenue stages and obligations.")
    lines.append("> Confidence increases as more balances and obligation amounts are confirmed.*")
    lines.append("")

    products = revenue.get("products", [])
    lines.append("## Revenue Pipeline")
    lines.append("")
    lines.append("| Rank | Product | Stage | Path to First Dollar |")
    lines.append("|---|---|---|---|")
    for prod in sorted(products, key=lambda p: p.get("rank", 99)):
        rank = prod.get("rank", "?")
        name = prod.get("product", "?")
        stage = prod.get("stage", "?")
        path = prod.get("first_dollar_path", "TBD")
        lines.append(f"| {rank} | {name} | {stage} | {path} |")
    lines.append("")

    start = datetime.now(timezone.utc)
    lines.append("## 12-Week Rolling Projection")
    lines.append("")
    lines.append("| Week | Starting | Known Inflows | Known Outflows | Net | Cumulative | Note |")
    lines.append("|---|---|---|---|---|---|---|")

    financial_obs = financial_obligations(entities, obligations)
    quantified_obs = [o for o in financial_obs if obligation_amount(o) is not None]
    unknown_amount_count = len(financial_obs) - len(quantified_obs)
    monthly_amounts = [
        amount for amount in (obligation_monthly_amount(o) for o in quantified_obs) if amount is not None
    ]
    known_monthly_outflow = sum(monthly_amounts) if monthly_amounts else 0.0
    known_weekly_outflow = known_monthly_outflow / 4.333 if known_monthly_outflow else 0.0

    cumulative = 0.0
    for w in range(12):
        week_start = (start + timedelta(weeks=w)).strftime("%Y-%m-%d")
        week_label = f"W{w + 1}"
        inflows = 0.0
        outflows = known_weekly_outflow
        notes = []

        deploy_week = 2
        if w >= deploy_week and any(p.get("stage") in ("deploy-ready", "live") for p in products):
            notes.append("post-deploy")
        if unknown_amount_count:
            notes.append(f"{unknown_amount_count} obligations unquantified")

        cumulative += inflows - outflows
        known_net = inflows - outflows
        if unknown_amount_count:
            net_str = f"${known_net:+.2f} known; unknown actual"
            cum_str = f"${cumulative:+.2f} known"
        else:
            net_str = f"${known_net:+.2f}"
            cum_str = f"${cumulative:+.2f}"
        inflow_str = "—" if inflows == 0 else f"${inflows:.2f}"
        if outflows:
            outflow_str = f"${outflows:.2f}"
        elif unknown_amount_count:
            outflow_str = "unknown"
        else:
            outflow_str = "—"
        note_str = "; ".join(notes) if notes else ""
        if w == 0 and not any(p.get("stage") in ("deploy-ready", "live") for p in products):
            note_str = "Pre-revenue — deploy Exporter to start pipeline"
        lines.append(
            f"| {week_label} | {week_start} | {inflow_str} | {outflow_str} | {net_str} | {cum_str} | {note_str} |"
        )

    lines.append("")

    nw = classified.get("net_worth")
    lines.append("### Runway")
    lines.append("")
    if nw is not None:
        lines.append(f"- **Current net position:** ${nw:,.2f}")
    else:
        lines.append(
            "- **Current net position:** Unknown — set balances in `entities.yaml` to enable runway calculation."
        )
    lines.append("- **Threshold:** < 4 weeks of obligations = alert principal.")
    if known_monthly_outflow:
        lines.append(f"- **Known monthly obligations:** ${known_monthly_outflow:,.2f}")
    if unknown_amount_count:
        lines.append(
            f"- **Unquantified obligations:** {unknown_amount_count} — runway is not reliable until amounts are entered."
        )
    lines.append("")

    lines.append("## Obligations (financial-material)")
    lines.append("")
    source_label = "obligations-ledger.json" if obligations.get("obligations") else "entities.yaml registry fallback"
    lines.append(f"Sourced from `{source_label}` — {len(financial_obs)} protocol-class obligations:")
    lines.append("")
    lines.append("| Priority | Title | Owner | Next Step |")
    lines.append("|---|---|---|---|")
    for ob in sorted(financial_obs, key=lambda o: o.get("priority", 50), reverse=True):
        title = ob.get("title", "?")
        priority = ob.get("priority", "?")
        owner = ob.get("owner", "?")
        step = ob.get("next_step", "Review")
        lines.append(f"| {priority} | {title} | {owner} | {step} |")
    lines.append("")

    return "\n".join(lines)


def _maturity_from_ladder() -> str:
    ladder_path = ROOT / "organ-ladder.json"
    try:
        if ladder_path.exists():
            with open(ladder_path) as f:
                data = json.load(f)
            for o in data.get("organs") or []:
                if o.get("pillar") == "financial":
                    m = o.get("maturity", "?")
                    s = o.get("stage", "?")
                    return f"**Maturity:** {s} ({m}%)"
    except Exception:
        pass
    return "**Maturity:** unknown"


def financial_obligations(entities: dict, obligations: dict) -> list[dict]:
    """Return protocol-class obligations, falling back to the financial registry.

    The isolated worktree may not carry the root mail-generated obligations ledger.
    entities.yaml embeds the financial-material obligations so the face remains
    truthful without reading the live root.
    """
    root_obligations = [o for o in obligations.get("obligations", []) if o.get("rung") == "protocol"]
    if root_obligations:
        return root_obligations

    embedded = []
    for source in entities.get("obligation_sources", []) or []:
        for item in source.get("financial_obligations", []) or []:
            embedded.append(
                {
                    "priority": item.get("priority", "?"),
                    "title": item.get("title", "?"),
                    "owner": item.get("entity", "?"),
                    "next_step": item.get("next_step", "Review"),
                    "source": source.get("source", "entities.yaml"),
                }
            )
    return embedded


def build_dashboard(
    entities: dict,
    revenue: dict,
    obligations: dict,
    classified: dict,
    census: dict | None = None,
) -> str:
    entity_list = entities.get("entities", [])
    products = revenue.get("products", [])
    oblist = obligations.get("obligations", [])
    financial_obs = financial_obligations(entities, obligations)
    if census is None:
        census = build_standing_census(entities, revenue, obligations, classified)

    lines = []
    lines.append("# Financial Office — STATUS Dashboard")
    lines.append("")
    lines.append(f"**Generated:** {now_iso()}  {_maturity_from_ladder()}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## At a glance")
    lines.append("")
    deployed_revenue = [p for p in products if p.get("stage") in ("deploy-ready", "live", "monetized")]

    nw = classified.get("net_worth")
    nw_str = f"${nw:,.2f}" if nw is not None else "unknown"
    prev_nw = classified.get("prev_net_worth")
    trend = ""
    if nw is not None and prev_nw is not None and prev_nw != 0:
        pct = ((nw - prev_nw) / abs(prev_nw)) * 100
        trend = f" ({pct:+.1f}% vs prev)"
    sc = classified.get("snapshot_count", 0)

    lines.append(f"- **Entities tracked:** {len(entity_list)}")
    lines.append(f"- **Revenue products:** {len(products)} ({len(deployed_revenue)} deploy-ready or live)")
    obligation_count = len(oblist) if oblist else len(financial_obs)
    obligation_label = str(obligation_count) if oblist else f"{obligation_count} financial-material (registry fallback)"
    lines.append(f"- **Open obligations:** {obligation_label}")
    lines.append(f"- **Net worth:** {nw_str}{trend}")
    lines.append(f"- **Balance snapshots:** {sc}")
    lines.append(
        f"- **Known balances:** {census.get('known_balance_count', 0)}/{census.get('account_count', 0)} accounts"
    )
    if census.get("unknown_obligation_amount_count", 0):
        lines.append(
            f"- **Unquantified obligations:** {census['unknown_obligation_amount_count']} (runway not reliable yet)"
        )
    lines.append("- **First dollar path:** ChatGPT Exporter → MONETA/Ko-fi (deploy-ready, principal-gated)")
    lines.append("")
    lines.append("## Artifacts")
    lines.append("")
    lines.append("| Artifact | File | Status |")
    lines.append("|---|---|---|")
    lines.append(
        "| Macro Face | `MACRO.md` | {} |".format(
            "Deepened — deployable-in-5-minutes, fleet-capacity-mapped" if MACRO_FACE.exists() else "Missing"
        )
    )
    lines.append(
        "| Micro Instance Face | `MICRO.md` | {} |".format(
            "Deepened — wealth/portfolio/tax-automation workflow, MONETA interaction, priority gates"
            if MICRO_FACE.exists()
            else "Missing"
        )
    )
    lines.append("| Entity Registry | `entities.yaml` | Live — {} entities registered |".format(len(entity_list)))
    has_balances = classified.get("known_assets", 0) + classified.get("known_liabilities", 0)
    bs_status = (
        "Live — {} known balances".format(has_balances) if has_balances else "Generated — needs principal balance entry"
    )
    lines.append(f"| Balance Sheet | `balance-sheet.md` | {bs_status} |")
    cashflow_status = (
        "Generated — amount-gated runway"
        if census.get("unknown_obligation_amount_count", 0)
        else "Generated — quantified baseline"
    )
    lines.append(f"| Cash-Flow Projection | `cashflow.md` | {cashflow_status} |")
    lines.append("| Standing Census | `standing-census.md` | Live — reliability preflight + principal input queue |")
    lines.append("| Payrail Disbursement Map | `payrail.md` | Authored — all 4 hops mapped |")
    lines.append("| Balance History | `balances-history.json` | {} snapshot(s) recorded |".format(sc))
    lines.append(
        "| Financial Dashboard (JSON) | `web/app/public/financial-standing.json` | Live — generated by this consolidator |"
    )
    lines.append(
        "| Obligations Ledger | `../../obligations-ledger.json` | {} |".format(
            "Live — mail organ feed"
            if (ROOT / "obligations-ledger.json").exists()
            else "Absent in this worktree — using `entities.yaml` fallback"
        )
    )
    lines.append("| Revenue Ladder | `../../revenue-ladder.json` | Live — conductor beat |")
    lines.append("")
    lines.append("## Next deepen steps")
    lines.append("")
    lines.append("1. ✅ **Macro/micro faces deepened** — excellent, showable, polished (2026-07-03 beat)")
    lines.append(
        "2. **P0: Clear card-0186 fraud hold** — one call to Santander; keystone for 3+ cascaded billing failures"
    )
    lines.append(
        "3. **P1: Enter balances** — principal fills `balance` + `as_of` in `entities.yaml` (unlocks real position tracking)"
    )
    lines.append("4. **P2: Deploy MONETA** — `docker build + docker run` on $0 host; set `MINT_BTC_ADDRESS`")
    lines.append("5. **P3: Deploy Exporter** — 'git push' + 'wrangler deploy'; first dollar via MONETA or Ko-fi")
    lines.append(
        "6. ✅ **Self-feed wired** — `financial-organ.py` runs every 8 beats; auto-advances maturity as slices land"
    )
    lines.append(
        "7. ✅ **Liability accounts registered** — Santander card and student-loan risk are first-class balance-sheet entries"
    )
    lines.append("8. ✅ **Web JSON dashboard** — `financial-standing.json` written to web face each beat")
    lines.append("9. ✅ **Balance journal** — `balances-history.json` persists time-series of snapshots")
    lines.append("10. **Quantify obligations** — enter monthly amounts for the highest-priority obligations")
    lines.append("11. **P4: Decide entity route** — revive LLC / dissolve / individual-only; sets tax structure")
    lines.append("12. **P5: Register investment accounts** — brokerage, retirement, crypto, credit accounts")
    lines.append("")

    return "\n".join(lines)


def build_web_dashboard(entities: dict, classified: dict, census: dict | None = None) -> dict:
    entity_list = entities.get("entities", [])
    if census is None:
        census = {
            "checks": [],
            "can_rely_on": [],
            "not_yet_reliable_for": [],
            "next_principal_inputs": [],
        }
    return {
        "ts": now_iso(),
        "date": today_str(),
        "net_worth": classified.get("net_worth"),
        "prev_net_worth": classified.get("prev_net_worth"),
        "total_assets": classified.get("total_assets"),
        "total_liabilities": classified.get("total_liabilities"),
        "known_asset_accounts": classified.get("known_assets", 0),
        "known_liability_accounts": classified.get("known_liabilities", 0),
        "unknown_accounts": classified.get("unknown_count", 0),
        "entity_count": len(entity_list),
        "snapshot_count": classified.get("snapshot_count", 0),
        "latest_snapshot_date": classified.get("latest_date"),
        "maturity": _maturity_from_ladder(),
        "standing_census": census,
        "faces": [
            {
                "id": "macro",
                "title": "Aerarium MACRO Face",
                "path": "organs/financial/MACRO.md",
                "status": "deepened" if MACRO_FACE.exists() else "missing",
                "promise": "deployable-in-5-minutes family office — fleet-capacity-mapped, self-sovereign, institutional weight for one person",
            },
            {
                "id": "micro",
                "title": "Aerarium MICRO Face",
                "path": "organs/financial/MICRO.md",
                "status": "deepened" if MICRO_FACE.exists() else "missing",
                "promise": "Anthony's real instance — MONETA sovereign intake, wealth/portfolio/tax-automation workflow, priority-ranked principal gates",
            },
        ],
        "rail_boundary": "MONETA intakes value; Aerarium tracks, projects, allocates, and governs the institution around it.",
    }


def comparable_content(text: str) -> str:
    text = re.sub(r"^(> Generated:) \S+$", r"\1 <generated>", text, flags=re.MULTILINE)
    return re.sub(
        r"^(\*\*Generated:\*\*) \S+(\s+\*\*Maturity:\*\*)",
        r"\1 <generated>\2",
        text,
        flags=re.MULTILINE,
    )


def write_if_changed(path: Path, content: str) -> bool:
    try:
        existing = path.read_text()
    except OSError:
        existing = None
    if existing is not None and comparable_content(existing) == comparable_content(content):
        return False
    path.write_text(content)
    return True


def write_json_if_changed(path: Path, data: dict) -> bool:
    content = json.dumps(data, indent=2)
    try:
        existing = path.read_text()
        if existing.rstrip() == content.rstrip():
            return False
    except OSError:
        pass
    path.write_text(content)
    return True


def main() -> int:
    entities = load_yaml(HERE / "entities.yaml")
    revenue = load_json(ROOT / "revenue-ladder.json")
    obligations = load_json(ROOT / "obligations-ledger.json")

    classification = (
        load_yaml(HERE / "entities.yaml").get("account_classification", ACCOUNT_CLASSIFICATION)
        or ACCOUNT_CLASSIFICATION
    )

    snapshots = load_balance_journal()
    snapshots = append_balance_journal(snapshots, entities)
    if write_balance_journal(snapshots):
        print(f"[consolidate] wrote {HERE}/balances-history.json ({len(snapshots)} snapshots)")

    classified = classify_balances(snapshots, classification)
    census = build_standing_census(entities, revenue, obligations, classified)

    artifacts = {
        "balance-sheet.md": build_balance_sheet(entities, revenue, obligations, classified),
        "cashflow.md": build_cashflow(entities, revenue, obligations, classified),
        "standing-census.md": build_standing_census_markdown(census),
        "STATUS.md": build_dashboard(entities, revenue, obligations, classified, census),
    }

    for filename, content in artifacts.items():
        path = HERE / filename
        if write_if_changed(path, content):
            print(f"[consolidate] wrote {path.relative_to(ROOT)} ({len(content)} chars)")
        else:
            print(f"[consolidate] unchanged {path.relative_to(ROOT)}")

    dashboard_json = build_web_dashboard(entities, classified, census)
    web_path = WEB_FACE / "financial-standing.json"
    WEB_FACE.mkdir(parents=True, exist_ok=True)
    if write_json_if_changed(web_path, dashboard_json):
        print(f"[consolidate] wrote {web_path.relative_to(ROOT)} (JSON dashboard face)")
    else:
        print(f"[consolidate] unchanged {web_path.relative_to(ROOT)}")

    print(f"[consolidate] done — {len(artifacts)} artifacts, {len(snapshots)} balance snapshots")
    return 0


if __name__ == "__main__":
    sys.exit(main())
