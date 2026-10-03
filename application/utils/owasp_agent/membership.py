"""OWASP membership dues helpers (regional / student / renew).

Prices mirror https://owasp.org/membership/ and the Foundation membership policy.
Regional eligibility uses ``countries.json`` ``discount: true`` from owasp.github.io.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

MEMBERSHIP_URL = "https://owasp.org/membership/"
MEMBERSHIP_POLICY_URL = "https://owasp.org/policy/membership"
RENEW_HINT = (
    f"Renew or join at {MEMBERSHIP_URL} "
    "(Glue Up membership portal). Members get renewal reminders ~60 days before expiry; "
    "you are responsible for renewing on time."
)

# Standard vs regional (developing economy) vs student — USD.
PRICES = {
    "standard": {
        "one_year": 50,
        "two_year": 95,
        "lifetime": 500,
        "student_one_year": 20,
    },
    "regional": {
        "one_year": 20,
        "two_year": 35,
        "lifetime": 200,
        "student_one_year": 8,
    },
}


def normalize_country(name: str) -> str:
    t = " ".join((name or "").strip().lower().split())
    aliases = {
        "usa": "united states",
        "us": "united states",
        "u.s.": "united states",
        "u.s.a.": "united states",
        "united states of america": "united states",
        "uk": "united kingdom",
        "great britain": "united kingdom",
    }
    return aliases.get(t, t)


def country_is_regional(
    country: str, discount_countries: Optional[Sequence[str]] = None
) -> Optional[bool]:
    """Return True/False when known; None when country not in the discount table."""
    target = normalize_country(country)
    if not target:
        return None
    if discount_countries is not None:
        table = {normalize_country(c): True for c in discount_countries}
        # Also need non-discount countries — caller should pass full map when possible.
        return table.get(target)
    return None


def resolve_tier(
    country: Optional[str],
    *,
    student: bool = False,
    country_discount_map: Optional[Dict[str, bool]] = None,
) -> Tuple[str, Dict[str, int], Optional[bool]]:
    """Return (tier_name, price_dict, regional_flag)."""
    regional: Optional[bool] = None
    if country and country_discount_map is not None:
        regional = country_discount_map.get(normalize_country(country))
    elif country:
        # Fail closed on unknown country list: treat as unknown, still quote both.
        regional = None

    if regional is True:
        tier = "regional"
    elif regional is False:
        tier = "standard"
    else:
        tier = "standard"  # default quote; message should note uncertainty if needed

    prices = dict(PRICES[tier])
    if student and regional is True:
        # Student in developing economy: $8 per policy.
        pass
    return tier, prices, regional


def format_membership_answer(
    *,
    country: Optional[str] = None,
    student: bool = False,
    compare_countries: Optional[Sequence[str]] = None,
    country_discount_map: Optional[Dict[str, bool]] = None,
    renew_only: bool = False,
) -> Dict[str, Any]:
    if renew_only:
        return {
            "ok": True,
            "message": RENEW_HINT + f" Policy: {MEMBERSHIP_POLICY_URL}.",
            "data": {"url": MEMBERSHIP_URL, "policy": MEMBERSHIP_POLICY_URL},
            "citations": [MEMBERSHIP_URL, MEMBERSHIP_POLICY_URL],
        }

    countries = list(compare_countries or [])
    if country and country not in countries:
        countries = [country] + countries

    if not countries:
        std = PRICES["standard"]
        reg = PRICES["regional"]
        msg = (
            f"OWASP individual membership (USD): standard ${std['one_year']}/year "
            f"(${std['two_year']}/2yr, lifetime ${std['lifetime']}); "
            f"student ${std['student_one_year']}/year; "
            f"regional/developing-economy ${reg['one_year']}/year "
            f"(${reg['two_year']}/2yr, lifetime ${reg['lifetime']}; "
            f"student ${reg['student_one_year']}/year). {RENEW_HINT}"
        )
        return {
            "ok": True,
            "message": msg,
            "data": {"prices": PRICES},
            "citations": [MEMBERSHIP_URL, MEMBERSHIP_POLICY_URL],
        }

    lines: List[str] = []
    rows: List[Dict[str, Any]] = []
    for c in countries:
        tier, prices, regional = resolve_tier(
            c, student=student, country_discount_map=country_discount_map
        )
        if regional is True:
            label = "regional (developing economy)"
        elif regional is False:
            label = "standard"
        else:
            label = (
                "standard (country not in discount table — confirm on membership page)"
            )
        if student:
            fee = prices["student_one_year"]
            lines.append(f"{c}: student ${fee} USD/year ({label}).")
        else:
            lines.append(
                f"{c}: {label} — ${prices['one_year']}/year, "
                f"${prices['two_year']}/2yr, lifetime ${prices['lifetime']} USD"
                + (
                    f"; student ${prices['student_one_year']}/year"
                    if not student
                    else ""
                )
                + "."
            )
        rows.append(
            {
                "country": c,
                "tier": tier,
                "regional": regional,
                "prices": prices,
                "student": student,
            }
        )

    msg = " ".join(lines) + " " + RENEW_HINT
    return {
        "ok": True,
        "message": msg,
        "data": {"rows": rows, "url": MEMBERSHIP_URL},
        "citations": [MEMBERSHIP_URL, MEMBERSHIP_POLICY_URL],
    }
