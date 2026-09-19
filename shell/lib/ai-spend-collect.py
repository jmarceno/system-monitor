#!/usr/bin/env python3
"""Read-only AI-spend snapshot for the system-monitor sidecar.

Fetches billing/quota from official APIs where they exist, plus the
undocumented-but-working Cursor dashboard RPC and OpenCode Go usage
endpoint. Credentials are discovered locally (never printed):

  1. ~/.config/qs-system-monitor/ai-spend.json  (optional secrets file)
  2. environment variables
  3. Cursor state.vscdb / OpenCode auth.json already on this machine

Stdout is one JSON object. Stderr is diagnostics with no secrets.
"""
from __future__ import annotations

import calendar
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

USER_AGENT = "qs-system-monitor/0.1"
HTTP_TIMEOUT_S = 8
CURSOR_OAUTH_CLIENT_ID = "KbZUR41cY7W6zRSdpSUJ7I7mLYBKOCmB"
CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"

PROVIDER_ORDER = (
    "codex",
    "opencode-go",
    "cursor",
    "openrouter",
    "deepseek",
    "openai",
    "meta",
)


# ---------------------------------------------------------------------------
# Paths (XDG, never a hardcoded user home)
# ---------------------------------------------------------------------------

def _xdg_config() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def _xdg_data() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))


def secrets_path() -> Path:
    override = os.environ.get("QS_AI_SPEND_SECRETS", "").strip()
    if override:
        return Path(override)
    return _xdg_config() / "qs-system-monitor" / "ai-spend.json"


def cursor_state_db() -> Path:
    override = os.environ.get("QS_CURSOR_STATE_DB", "").strip()
    if override:
        return Path(override)
    return _xdg_config() / "Cursor" / "User" / "globalStorage" / "state.vscdb"


def opencode_auth_path() -> Path:
    override = os.environ.get("QS_OPENCODE_AUTH", "").strip()
    if override:
        return Path(override)
    return _xdg_data() / "opencode" / "auth.json"


def codex_auth_path() -> Path:
    override = os.environ.get("QS_CODEX_AUTH", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".codex" / "auth.json"


# ---------------------------------------------------------------------------
# Formatting / snapshot helpers
# ---------------------------------------------------------------------------

def fmt_usd(n: Any) -> str:
    if not isinstance(n, (int, float)) or n != n:  # NaN
        return "n/a"
    sign = "-" if n < 0 else ""
    return f"{sign}${abs(n):.2f}"


def fmt_pct(n: Any) -> str:
    if not isinstance(n, (int, float)) or n != n:
        return "n/a"
    return f"{int(round(n))}%"


def cents_to_usd(cents: Any) -> float | None:
    """Cursor dashboard amounts are integer USD cents."""
    if isinstance(cents, bool) or not isinstance(cents, (int, float)) or cents != cents:
        return None
    return float(cents) / 100.0


def parse_amount(value: Any) -> float | None:
    """DeepSeek balances are decimal strings ("110.00"); accept those too."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value == value else None
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def fmt_balance(amount: Any, currency: str = "USD") -> str:
    """Currency-aware balance headline (DeepSeek reports CNY or USD)."""
    parsed = parse_amount(amount)
    if parsed is None or parsed != parsed:
        return "n/a"
    cur = (currency or "USD").strip().upper()
    if cur == "USD":
        return fmt_usd(parsed)
    if cur == "CNY":
        return f"¥{parsed:.2f}"
    return f"{parsed:.2f} {cur}" if cur else fmt_usd(parsed)


def parse_when(value: Any) -> str:
    """Format a unix-ms, unix-s, or ISO-8601 timestamp for the sidecar."""
    if value is None or value == "":
        return "n/a"
    dt: datetime | None = None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        elif ts > 1e10:
            ts /= 1000.0
        try:
            dt = datetime.fromtimestamp(ts)
        except (OverflowError, OSError, ValueError):
            dt = None
    elif isinstance(value, str):
        s = value.strip()
        if s.isdigit():
            return parse_when(int(s))
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
        except ValueError:
            dt = None
    if dt is None:
        return "n/a"
    return dt.strftime("%-d %b %H:%M") if os.name != "nt" else dt.strftime("%d %b %H:%M")


def provider(
    pid: str,
    name: str,
    *,
    status: str,
    unofficial: bool = False,
    headline: str = "n/a",
    headline_label: str = "",
    pct: float | None = None,
    detail: str = "",
    note: str = "",
    lines: list[dict[str, str]] | None = None,
    meters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": pid,
        "name": name,
        "status": status,  # ok | na | error
        "unofficial": unofficial,
        "headline": headline,
        "headlineLabel": headline_label,
        "pct": pct if isinstance(pct, (int, float)) and pct == pct else None,
        "detail": detail,
        "note": note,
        "lines": lines or [],
        "meters": meters or [],
    }


def _na(pid: str, name: str, note: str, unofficial: bool = False) -> dict[str, Any]:
    return provider(pid, name, status="na", unofficial=unofficial, note=note)


def _err(pid: str, name: str, note: str, unofficial: bool = False) -> dict[str, Any]:
    return provider(pid, name, status="error", unofficial=unofficial, note=note)


# ---------------------------------------------------------------------------
# Credential loading (values never logged)
# ---------------------------------------------------------------------------

def load_secrets_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("ai-spend: secrets file unreadable", file=sys.stderr)
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, val in raw.items():
        if isinstance(val, str) and val.strip():
            out[str(key)] = val.strip()
    return out


def load_opencode_auth(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("ai-spend: opencode auth.json unreadable", file=sys.stderr)
        return {}
    return raw if isinstance(raw, dict) else {}


def load_codex_auth(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("ai-spend: codex auth.json unreadable", file=sys.stderr)
        return {}
    return raw if isinstance(raw, dict) else {}


def codex_tokens(auth: dict[str, Any]) -> tuple[str, str, str]:
    """Return (access_token, refresh_token, account_id) from Codex CLI auth.json."""
    nested = auth.get("tokens") if isinstance(auth.get("tokens"), dict) else {}
    access = first_nonempty(
        nested.get("access_token", "") if isinstance(nested.get("access_token"), str) else "",
        auth.get("access_token", "") if isinstance(auth.get("access_token"), str) else "",
    )
    refresh = first_nonempty(
        nested.get("refresh_token", "") if isinstance(nested.get("refresh_token"), str) else "",
        auth.get("refresh_token", "") if isinstance(auth.get("refresh_token"), str) else "",
    )
    account = first_nonempty(
        nested.get("account_id", "") if isinstance(nested.get("account_id"), str) else "",
        auth.get("account_id", "") if isinstance(auth.get("account_id"), str) else "",
    )
    return access, refresh, account


def auth_key(auth: dict[str, Any], provider_id: str) -> str:
    entry = auth.get(provider_id)
    if not isinstance(entry, dict):
        return ""
    key = entry.get("key") or entry.get("apiKey") or ""
    return key.strip() if isinstance(key, str) else ""


def cursor_item(db_path: Path, key: str) -> str:
    if not db_path.is_file():
        return ""
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = con.execute(
                "SELECT value FROM ItemTable WHERE key = ?", (key,)
            ).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        print("ai-spend: cursor state db unreadable", file=sys.stderr)
        return ""
    if not row or row[0] is None:
        return ""
    return str(row[0])


def first_nonempty(*vals: str) -> str:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


# ---------------------------------------------------------------------------
# HTTP (User-Agent required: Cloudflare 1010's Python-urllib's default UA)
# ---------------------------------------------------------------------------

def http_json(
    url: str,
    token: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int | None, Any, str]:
    """Return (status, parsed_json_or_None, error_note). Never includes the token."""
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8", "replace")
            status = getattr(resp, "status", 200)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        return e.code, _try_json(raw), _http_note(e.code)
    except urllib.error.URLError:
        return None, None, "unreachable"
    except Exception:
        return None, None, "request failed"
    parsed = _try_json(raw)
    if parsed is None:
        return status, None, "unexpected response"
    return status, parsed, ""


def _try_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _http_note(code: int) -> str:
    if code in (401, 403):
        return "unauthorized"
    if code == 404:
        return "not found"
    if code == 429:
        return "rate limited"
    return f"http {code}"


# ---------------------------------------------------------------------------
# Parsers (layout-tolerant; unknown fields ignored)
# ---------------------------------------------------------------------------

def _pct_field(obj: Any, key: str) -> float | None:
    if not isinstance(obj, dict):
        return None
    v = obj.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        return None
    return float(v)


def _on_demand_label(hard_limit: Any) -> str | None:
    """Match the Plan & Usage page: on-demand is a toggle, not bonusSpend cents."""
    if not isinstance(hard_limit, dict):
        return None
    if hard_limit.get("noUsageBasedAllowed") is True:
        return "off"
    cap = hard_limit.get("hardLimit")
    if isinstance(cap, (int, float)) and not isinstance(cap, bool) and cap > 0:
        return f"{fmt_usd(cap)} cap"
    if hard_limit.get("noUsageBasedAllowed") is False:
        return "on"
    return None


def parse_cursor_usage(
    payload: Any,
    plan_name: str = "",
    hard_limit: Any = None,
) -> dict[str, Any]:
    """Pro plan meters, not list-price cents.

    GetCurrentPeriodUsage.planUsage.includedSpend/limit/totalSpend are dollar
    bookkeeping (often plan-price-shaped) and displayMessage can say "hit your
    usage limit" while autoPercentUsed/apiPercentUsed are the dashboard bars
    (Cursor models / Other models). Those percents are the source of truth.
    """
    if not isinstance(payload, dict):
        return _err("cursor", "Cursor", "unexpected response", unofficial=True)
    pu = payload.get("planUsage") if isinstance(payload.get("planUsage"), dict) else {}
    auto = _pct_field(pu, "autoPercentUsed")
    other = _pct_field(pu, "apiPercentUsed")
    combined = _pct_field(pu, "totalPercentUsed")

    meters: list[dict[str, Any]] = []
    if auto is not None:
        meters.append({"label": "Cursor models", "pct": auto})
    if other is not None:
        meters.append({"label": "Other models", "pct": other})
    if not meters and combined is not None:
        meters.append({"label": "Plan used", "pct": combined})

    used = [m["pct"] for m in meters]
    bar_pct = max(used) if used else None
    if auto is not None and other is not None:
        headline = f"{fmt_pct(auto)} / {fmt_pct(other)}"
        headline_label = "cursor / other"
    elif bar_pct is not None:
        headline = fmt_pct(bar_pct)
        headline_label = "used"
    else:
        headline = "n/a"
        headline_label = "used"

    lines: list[dict[str, str]] = []
    on_demand = _on_demand_label(hard_limit)
    if on_demand:
        lines.append({"label": "On-demand", "value": on_demand})
    lines.append({"label": "Resets", "value": parse_when(payload.get("billingCycleEnd"))})

    title = "Cursor" + (f" · {plan_name}" if plan_name else "")
    return provider(
        "cursor",
        title,
        status="ok",
        unofficial=True,
        headline=headline,
        headline_label=headline_label,
        pct=bar_pct,
        note="Unofficial dashboard API",
        lines=lines,
        meters=meters,
    )


def parse_openrouter_credits(payload: Any, key_payload: Any = None) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return _err("openrouter", "OpenRouter", "unexpected response")
    credits = data.get("total_credits")
    usage = data.get("total_usage")
    remaining = None
    pct = None
    if isinstance(credits, (int, float)) and isinstance(usage, (int, float)):
        remaining = credits - usage
        if credits > 0:
            pct = 100.0 * usage / credits
    monthly = None
    kd = key_payload.get("data") if isinstance(key_payload, dict) else None
    if isinstance(kd, dict) and isinstance(kd.get("usage_monthly"), (int, float)):
        monthly = kd.get("usage_monthly")
    lines = []
    if monthly is not None:
        lines.append({"label": "This month", "value": fmt_usd(monthly)})
    return provider(
        "openrouter",
        "OpenRouter",
        status="ok",
        headline=fmt_usd(remaining) if remaining is not None else "n/a",
        headline_label="remaining",
        pct=pct,
        detail=f"{fmt_usd(usage)} used of {fmt_usd(credits)}" if credits is not None else "",
        lines=lines,
    )


def deepseek_is_peak(now: datetime | None = None) -> bool:
    """DeepSeek peak windows: 01:00-04:00 and 06:00-10:00 UTC, Mon-Fri.

    https://api-docs.deepseek.com/quick_start/pricing — off-peak calls are
    discounted, so the sidecar flags the current window. Bounds are
    start-inclusive, end-exclusive; weekends are always off-peak.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if now.weekday() >= 5:
        return False
    mins = now.hour * 60 + now.minute
    return (60 <= mins < 240) or (360 <= mins < 600)


def parse_deepseek_balance(payload: Any, now: datetime | None = None) -> dict[str, Any]:
    """Official GET /user/balance: is_available + per-currency balance_infos.

    Docs: https://api-docs.deepseek.com/api/get-user-balance
    Each entry: {currency: CNY|USD, total_balance: "110.00",
    granted_balance: "10.00", topped_up_balance: "100.00"} — amounts are
    decimal strings. Prefer USD when several currencies are present.
    """
    if not isinstance(payload, dict):
        return _err("deepseek", "DeepSeek", "unexpected response")
    infos = payload.get("balance_infos")
    if not isinstance(infos, list):
        return _err("deepseek", "DeepSeek", "unexpected response")
    entries: list[dict[str, Any]] = []
    for info in infos:
        if not isinstance(info, dict):
            continue
        currency = info.get("currency") if isinstance(info.get("currency"), str) else ""
        total = parse_amount(info.get("total_balance"))
        if not currency or total is None:
            continue
        entries.append({
            "currency": currency.strip().upper(),
            "total": total,
            "granted": parse_amount(info.get("granted_balance")),
            "topped_up": parse_amount(info.get("topped_up_balance")),
        })
    if not entries:
        return _err("deepseek", "DeepSeek", "unexpected response")
    # Prefer USD so mixed-currency accounts show the familiar unit first.
    entries.sort(key=lambda e: 0 if e["currency"] == "USD" else 1)
    head = entries[0]
    lines: list[dict[str, str]] = []
    utc_now = now or datetime.now(timezone.utc)
    if utc_now.tzinfo is None:
        utc_now = utc_now.replace(tzinfo=timezone.utc)
    peak = deepseek_is_peak(utc_now)
    lines.append({
        # UTC stamp shows which clock the flag follows (local TZ may differ).
        "label": "Rate",
        "value": f"{'Peak' if peak else 'Off-peak'} · {utc_now:%H:%M} UTC",
        "tone": "bad" if peak else "good",  # sidecar colors this red/green
    })
    if head["granted"] is not None:
        lines.append({"label": "Granted", "value": fmt_balance(head["granted"], head["currency"])})
    if head["topped_up"] is not None:
        lines.append({"label": "Topped-up", "value": fmt_balance(head["topped_up"], head["currency"])})
    for other in entries[1:]:
        lines.append({
            "label": other["currency"],
            "value": fmt_balance(other["total"], other["currency"]),
        })
    available = payload.get("is_available")
    detail = ""
    if available is False:
        detail = "Not available for API calls"
    return provider(
        "deepseek",
        "DeepSeek",
        status="ok",
        headline=fmt_balance(head["total"], head["currency"]),
        headline_label="remaining",
        pct=None,  # prepaid balance has no quota total to percent against
        detail=detail,
        lines=lines,
    )


def parse_opencode_go_usage(payload: Any) -> dict[str, Any]:
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        return _err("opencode-go", "OpenCode Go", "unexpected response", unofficial=True)

    def window(w: Any) -> dict[str, Any]:
        if not isinstance(w, dict):
            return {"percent": None, "resetsAt": "n/a", "ok": False}
        pct = w.get("percent")
        return {
            "percent": float(pct) if isinstance(pct, (int, float)) else None,
            "resetsAt": parse_when(w.get("resetsAt")),
            "ok": w.get("status") == "ok" or isinstance(pct, (int, float)),
        }

    rolling = window(usage.get("rolling"))
    weekly = window(usage.get("weekly"))
    monthly = window(usage.get("monthly"))
    headline_pct = monthly["percent"]
    if headline_pct is None:
        headline_pct = weekly["percent"] if weekly["percent"] is not None else rolling["percent"]
    lines = [
        {"label": "5-hour", "value": f"{fmt_pct(rolling['percent'])} · {rolling['resetsAt']}"},
        {"label": "Weekly", "value": f"{fmt_pct(weekly['percent'])} · {weekly['resetsAt']}"},
        {"label": "Monthly", "value": f"{fmt_pct(monthly['percent'])} · {monthly['resetsAt']}"},
    ]
    return provider(
        "opencode-go",
        "OpenCode Go",
        status="ok",
        unofficial=True,
        headline=fmt_pct(headline_pct),
        headline_label="monthly used",
        pct=headline_pct,
        detail="Quota % — wallet balance is not in the API",
        note="Undocumented usage API",
        lines=lines,
    )


def parse_openai_costs(payload: Any) -> dict[str, Any]:
    buckets = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(buckets, list):
        return _err("openai", "OpenAI", "unexpected response")
    total = 0.0
    found = False
    for bucket in buckets:
        if not isinstance(bucket, dict):
            continue
        results = bucket.get("results")
        if not isinstance(results, list):
            continue
        for row in results:
            if not isinstance(row, dict):
                continue
            amount = row.get("amount")
            if not isinstance(amount, dict):
                continue
            val = amount.get("value")
            if isinstance(val, (int, float)):
                total += float(val)
                found = True
    if not found:
        return provider(
            "openai",
            "OpenAI",
            status="ok",
            headline=fmt_usd(0),
            headline_label="this month",
            pct=None,
            detail="No billed usage in range",
            lines=[{"label": "This month", "value": fmt_usd(0)}],
        )
    return provider(
        "openai",
        "OpenAI",
        status="ok",
        headline=fmt_usd(total),
        headline_label="this month",
        lines=[{"label": "This month", "value": fmt_usd(total)}],
    )


def _codex_window_label(seconds: Any) -> str:
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
        return "Window"
    s = int(seconds)
    if s == 18000:
        return "5-hour"
    if s == 604800:
        return "Weekly"
    if s >= 86400 and s % 86400 == 0:
        return f"{s // 86400}d"
    if s >= 3600 and s % 3600 == 0:
        return f"{s // 3600}h"
    return "Window"


def parse_codex_usage(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return _err("codex", "Codex", "unexpected response", unofficial=True)
    rl = payload.get("rate_limit") if isinstance(payload.get("rate_limit"), dict) else {}
    meters: list[dict[str, Any]] = []
    lines: list[dict[str, str]] = []
    pcts: list[float] = []
    for key, fallback in (("primary_window", "5-hour"), ("secondary_window", "Weekly")):
        win = rl.get(key) if isinstance(rl.get(key), dict) else {}
        pct = _pct_field(win, "used_percent")
        if pct is None:
            continue
        label = _codex_window_label(win.get("limit_window_seconds"))
        if label == "Window":
            label = fallback
        meters.append({"label": label, "pct": pct})
        pcts.append(pct)
        lines.append({"label": label, "value": f"{fmt_pct(pct)} · {parse_when(win.get('reset_at'))}"})

    credits = payload.get("credits") if isinstance(payload.get("credits"), dict) else {}
    balance = credits.get("balance")
    if credits.get("has_credits") or (isinstance(balance, str) and balance not in ("", "0", "0.00", "0.0")):
        lines.append({"label": "Credits", "value": str(balance)})

    plan = payload.get("plan_type")
    title = "Codex" + (f" · {plan}" if isinstance(plan, str) and plan.strip() else "")
    if len(pcts) >= 2:
        headline = f"{fmt_pct(pcts[0])} / {fmt_pct(pcts[1])}"
        headline_label = "5h / week"
    elif pcts:
        headline = fmt_pct(pcts[0])
        headline_label = "used"
    else:
        headline = "n/a"
        headline_label = "used"
    detail = ""
    if rl.get("limit_reached"):
        detail = "Rate limit reached"
    return provider(
        "codex",
        title,
        status="ok",
        unofficial=True,
        headline=headline,
        headline_label=headline_label,
        pct=max(pcts) if pcts else None,
        detail=detail,
        note="Undocumented ChatGPT usage API",
        lines=lines,
        meters=meters,
    )


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------

def fetch_cursor(secrets: dict[str, str], plan_name: str) -> dict[str, Any]:
    token = first_nonempty(
        secrets.get("cursorAccessToken", ""),
        os.environ.get("CURSOR_API_KEY", ""),
        cursor_item(cursor_state_db(), "cursorAuth/accessToken"),
    )
    if not token:
        return _na("cursor", "Cursor", "Sign in to Cursor (or add cursorAccessToken)", unofficial=True)

    def rpc(tok: str, method: str) -> tuple[int | None, Any, str]:
        return http_json(
            f"https://api2.cursor.sh/aiserver.v1.DashboardService/{method}",
            tok,
            method="POST",
            body=b"{}",
            extra_headers={
                "Content-Type": "application/json",
                "Connect-Protocol-Version": "1",
            },
        )

    status, payload, note = rpc(token, "GetCurrentPeriodUsage")
    if status in (401, 403):
        refreshed = _refresh_cursor_token()
        if refreshed:
            token = refreshed
            status, payload, note = rpc(token, "GetCurrentPeriodUsage")
    if status != 200 or not isinstance(payload, dict):
        return _err("cursor", "Cursor", note or "unavailable", unofficial=True)
    _, hard_limit, _ = rpc(token, "GetHardLimit")
    return parse_cursor_usage(payload, plan_name, hard_limit)


def _refresh_cursor_token() -> str:
    """In-memory refresh only — never writes back to Cursor's database."""
    refresh = cursor_item(cursor_state_db(), "cursorAuth/refreshToken")
    if not refresh:
        return ""
    body = json.dumps({
        "grant_type": "refresh_token",
        "client_id": CURSOR_OAUTH_CLIENT_ID,
        "refresh_token": refresh,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api2.cursor.sh/oauth/token",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            payload = _try_json(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return ""
    if not isinstance(payload, dict) or payload.get("shouldLogout"):
        return ""
    token = payload.get("access_token")
    return token.strip() if isinstance(token, str) else ""


def fetch_openrouter(secrets: dict[str, str], auth: dict[str, Any]) -> dict[str, Any]:
    token = first_nonempty(
        secrets.get("openrouterManagementKey", ""),
        secrets.get("openrouterKey", ""),
        os.environ.get("OPENROUTER_API_KEY", ""),
        auth_key(auth, "openrouter"),
    )
    if not token:
        return _na("openrouter", "OpenRouter", "Add openrouterKey to the secrets file")
    status, payload, note = http_json("https://openrouter.ai/api/v1/credits", token)
    if status != 200:
        return _err("openrouter", "OpenRouter", note or "unavailable")
    _, key_payload, _ = http_json("https://openrouter.ai/api/v1/key", token)
    return parse_openrouter_credits(payload, key_payload)


def fetch_deepseek(secrets: dict[str, str]) -> dict[str, Any]:
    token = first_nonempty(
        secrets.get("deepseekKey", ""),
        secrets.get("deepseekApiKey", ""),
        os.environ.get("DEEPSEEK_API_KEY", ""),
        os.environ.get("DEEPSEEK_KEY", ""),
    )
    if not token:
        return _na("deepseek", "DeepSeek", "Add deepseekKey to the secrets file")
    status, payload, note = http_json("https://api.deepseek.com/user/balance", token)
    if status != 200:
        return _err("deepseek", "DeepSeek", note or "unavailable")
    return parse_deepseek_balance(payload)


def fetch_opencode_go(secrets: dict[str, str], auth: dict[str, Any]) -> dict[str, Any]:
    token = first_nonempty(
        secrets.get("opencodeGoKey", ""),
        os.environ.get("OPENCODE_GO_API_KEY", ""),
        os.environ.get("OPENCODE_API_KEY", ""),
        auth_key(auth, "opencode-go"),
    )
    if not token:
        return _na(
            "opencode-go",
            "OpenCode Go",
            "Connect OpenCode Go (or add opencodeGoKey)",
            unofficial=True,
        )
    status, payload, note = http_json("https://opencode.ai/zen/go/v1/usage", token)
    if status != 200:
        return _err("opencode-go", "OpenCode Go", note or "unavailable", unofficial=True)
    return parse_opencode_go_usage(payload)


def fetch_openai(secrets: dict[str, str]) -> dict[str, Any]:
    token = first_nonempty(
        secrets.get("openaiAdminKey", ""),
        os.environ.get("OPENAI_ADMIN_KEY", ""),
    )
    if not token:
        return _na(
            "openai",
            "OpenAI",
            "Needs an organization admin key (openaiAdminKey)",
        )
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    last_day = calendar.monthrange(now.year, now.month)[1]
    # Costs API: start inclusive, end exclusive; default bucket is 1d.
    url = (
        "https://api.openai.com/v1/organization/costs"
        f"?start_time={int(start.timestamp())}"
        f"&limit={last_day}"
    )
    status, payload, note = http_json(url, token)
    if status != 200:
        return _err("openai", "OpenAI", note or "unavailable")
    return parse_openai_costs(payload)


def _refresh_codex_token(refresh: str) -> str:
    """In-memory refresh only — never writes ~/.codex/auth.json."""
    if not refresh:
        return ""
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "client_id": CODEX_OAUTH_CLIENT_ID,
        "refresh_token": refresh,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://auth.openai.com/oauth/token",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            payload = _try_json(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return ""
    if not isinstance(payload, dict):
        return ""
    token = payload.get("access_token")
    return token.strip() if isinstance(token, str) else ""


def fetch_codex(secrets: dict[str, str]) -> dict[str, Any]:
    auth = load_codex_auth(codex_auth_path())
    access, refresh, account_id = codex_tokens(auth)
    token = first_nonempty(secrets.get("codexAccessToken", ""), access)
    if not token:
        return _na("codex", "Codex", "Sign in to the Codex CLI", unofficial=True)
    extra = {}
    if account_id:
        extra["ChatGPT-Account-Id"] = account_id
    status, payload, note = http_json(
        "https://chatgpt.com/backend-api/wham/usage",
        token,
        extra_headers=extra or None,
    )
    if status in (401, 403) and refresh:
        refreshed = _refresh_codex_token(refresh)
        if refreshed:
            status, payload, note = http_json(
                "https://chatgpt.com/backend-api/wham/usage",
                refreshed,
                extra_headers=extra or None,
            )
    if status != 200 or not isinstance(payload, dict):
        return _err("codex", "Codex", note or "unavailable", unofficial=True)
    return parse_codex_usage(payload)


def fetch_meta() -> dict[str, Any]:
    return _na(
        "meta",
        "Meta AI",
        "No account-wide spend API (dashboard only)",
    )


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def collect() -> dict[str, Any]:
    secrets = load_secrets_file(secrets_path())
    auth = load_opencode_auth(opencode_auth_path())
    plan = cursor_item(cursor_state_db(), "cursorAuth/stripeMembershipType")

    jobs = {
        "cursor": lambda: fetch_cursor(secrets, plan),
        "opencode-go": lambda: fetch_opencode_go(secrets, auth),
        "openrouter": lambda: fetch_openrouter(secrets, auth),
        "deepseek": lambda: fetch_deepseek(secrets),
        "openai": lambda: fetch_openai(secrets),
        "codex": lambda: fetch_codex(secrets),
        "meta": fetch_meta,
    }
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=7) as pool:
        futs = {pool.submit(fn): pid for pid, fn in jobs.items()}
        for fut in as_completed(futs):
            pid = futs[fut]
            try:
                results[pid] = fut.result()
            except Exception:
                name = {
                    "cursor": "Cursor",
                    "opencode-go": "OpenCode Go",
                    "openrouter": "OpenRouter",
                    "deepseek": "DeepSeek",
                    "openai": "OpenAI",
                    "codex": "Codex",
                    "meta": "Meta AI",
                }.get(pid, pid)
                unofficial = pid in ("cursor", "opencode-go", "codex")
                results[pid] = _err(pid, name, "collector failed", unofficial=unofficial)

    providers = [results.get(pid) or _err(pid, pid, "missing") for pid in PROVIDER_ORDER]
    ok_n = sum(1 for p in providers if p.get("status") == "ok")
    return {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "okCount": ok_n,
        "providers": providers,
    }


# ---------------------------------------------------------------------------
# Self-test (no network, no secrets)
# ---------------------------------------------------------------------------

def _self_test() -> int:
    failures = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        if cond:
            print(f"  ok  {name}")
        else:
            failures += 1
            print(f"FAIL  {name} {detail}", file=sys.stderr)

    check("fmt_usd", fmt_usd(4.5) == "$4.50" and fmt_usd(-1) == "-$1.00")
    check("cents", cents_to_usd(21747) == 217.47)
    check("when ms", parse_when("1768399334000") != "n/a")

    cursor = parse_cursor_usage({
        "billingCycleEnd": "1771077734000",
        "displayMessage": "You've hit your usage limit",
        "planUsage": {
            "totalSpend": 21747,
            "includedSpend": 2000,
            "bonusSpend": 19747,
            "limit": 2000,
            "autoPercentUsed": 44.85,
            "apiPercentUsed": 46.4,
            "totalPercentUsed": 44.95,
        },
    }, "pro", {"hardLimit": 0, "noUsageBasedAllowed": True})
    check("cursor status", cursor["status"] == "ok")
    check("cursor headline", cursor["headline"] == "45% / 46%", cursor["headline"])
    check("cursor unofficial", cursor["unofficial"] is True)
    check("cursor ignores displayMessage", "hit" not in (cursor.get("detail") or "").lower())
    check("cursor meters", cursor["meters"][0]["label"] == "Cursor models")
    check("cursor on-demand", cursor["lines"][0]["value"] == "off", str(cursor["lines"]))
    check("cursor pct is max meter", abs(cursor["pct"] - 46.4) < 0.01, str(cursor["pct"]))

    fallback = parse_cursor_usage({"planUsage": {"totalPercentUsed": 15.48}})
    check("cursor fallback combined", fallback["headline"] == "15%", fallback["headline"])

    orr = parse_openrouter_credits(
        {"data": {"total_credits": 100.50, "total_usage": 25.75}},
        {"data": {"usage_monthly": 3.47}},
    )
    check("openrouter remaining", orr["headline"] == "$74.75", orr["headline"])
    check("openrouter monthly", orr["lines"][0]["value"] == "$3.47")
    check("openrouter no used/purchased", len(orr["lines"]) == 1, str(orr["lines"]))

    ds = parse_deepseek_balance({
        "is_available": True,
        "balance_infos": [{
            "currency": "CNY",
            "total_balance": "110.00",
            "granted_balance": "10.00",
            "topped_up_balance": "100.00",
        }],
    })
    check("deepseek status", ds["status"] == "ok")
    check("deepseek headline", ds["headline"] == "¥110.00", ds["headline"])
    check("deepseek granted", ds["lines"][1]["value"] == "¥10.00", str(ds["lines"]))
    check("deepseek topped-up", ds["lines"][2]["value"] == "¥100.00", str(ds["lines"]))
    check("deepseek no pct", ds["pct"] is None, str(ds["pct"]))

    check("deepseek peak mon 02:00",
          deepseek_is_peak(datetime(2026, 9, 14, 2, 0, tzinfo=timezone.utc)) is True)
    check("deepseek gap mon 05:00",
          deepseek_is_peak(datetime(2026, 9, 14, 5, 0, tzinfo=timezone.utc)) is False)
    check("deepseek peak mon 09:59",
          deepseek_is_peak(datetime(2026, 9, 14, 9, 59, tzinfo=timezone.utc)) is True)
    check("deepseek off mon 10:00",
          deepseek_is_peak(datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)) is False)
    check("deepseek weekend off",
          deepseek_is_peak(datetime(2026, 9, 12, 2, 0, tzinfo=timezone.utc)) is False)
    peak_ds = parse_deepseek_balance({
        "is_available": True,
        "balance_infos": [{"currency": "USD", "total_balance": "10.00",
                           "granted_balance": "0.00", "topped_up_balance": "10.00"}],
    }, now=datetime(2026, 9, 14, 7, 30, tzinfo=timezone.utc))
    check("deepseek rate peak",
          peak_ds["lines"][0] == {"label": "Rate", "value": "Peak · 07:30 UTC", "tone": "bad"},
          str(peak_ds["lines"][0]))
    off_ds = parse_deepseek_balance({
        "is_available": True,
        "balance_infos": [{"currency": "USD", "total_balance": "10.00",
                           "granted_balance": "0.00", "topped_up_balance": "10.00"}],
    }, now=datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc))
    check("deepseek rate off-peak",
          off_ds["lines"][0] == {"label": "Rate", "value": "Off-peak · 12:00 UTC", "tone": "good"},
          str(off_ds["lines"][0]))

    ds_usd = parse_deepseek_balance({
        "is_available": False,
        "balance_infos": [
            {"currency": "CNY", "total_balance": "5.00",
             "granted_balance": "0.00", "topped_up_balance": "5.00"},
            {"currency": "USD", "total_balance": "10.00",
             "granted_balance": "2.00", "topped_up_balance": "8.00"},
        ],
    })
    check("deepseek prefers USD", ds_usd["headline"] == "$10.00", ds_usd["headline"])
    check("deepseek unavailable detail", "not available" in (ds_usd.get("detail") or "").lower(),
          str(ds_usd.get("detail")))
    check("deepseek other currency line", any(line["label"] == "CNY" for line in ds_usd["lines"]),
          str(ds_usd["lines"]))
    check("deepseek bad payload", parse_deepseek_balance({"nope": True})["status"] == "error")

    go = parse_opencode_go_usage({
        "usage": {
            "rolling": {"percent": 39, "resetsAt": "2026-09-07T18:46:17.495Z", "status": "ok"},
            "weekly": {"percent": 15, "resetsAt": "2026-09-14T00:00:00.495Z", "status": "ok"},
            "monthly": {"percent": 13, "resetsAt": "2026-10-03T12:43:01.495Z", "status": "ok"},
        }
    })
    check("go headline", go["headline"] == "13%", go["headline"])
    check("go pct", go["pct"] == 13)

    oai = parse_openai_costs({
        "data": [{
            "object": "bucket",
            "results": [
                {"amount": {"value": 0.06, "currency": "usd"}},
                {"amount": {"value": 1.94, "currency": "usd"}},
            ],
        }]
    })
    check("openai sum", oai["headline"] == "$2.00", oai["headline"])

    codex = parse_codex_usage({
        "plan_type": "plus",
        "rate_limit": {
            "allowed": False,
            "limit_reached": True,
            "primary_window": {
                "used_percent": 100,
                "limit_window_seconds": 18000,
                "reset_at": 1788806635,
            },
            "secondary_window": {
                "used_percent": 61,
                "limit_window_seconds": 604800,
                "reset_at": 1789333713,
            },
        },
        "credits": {"has_credits": False, "balance": "0"},
    })
    check("codex headline", codex["headline"] == "100% / 61%", codex["headline"])
    check("codex plan", codex["name"] == "Codex · plus", codex["name"])
    check("codex 5h meter", codex["meters"][0]["label"] == "5-hour")
    check("codex limit detail", "limit" in (codex.get("detail") or "").lower())

    check("drift ignored", parse_cursor_usage({"planUsage": {"totalSpend": 100, "mystery": 1}})["status"] == "ok")
    check("bad payload", parse_openrouter_credits({"nope": True})["status"] == "error")

    if failures:
        print(f"\n{failures} check(s) FAILED", file=sys.stderr)
        return 1
    print("\nAll ai-spend parser checks passed.")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return _self_test()
    snapshot = collect()
    json.dump(snapshot, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
