from __future__ import annotations

import json

import pytest

from analytics import build_scorecard
from rulebook import validate_report


def test_structural_parser_error_blocks_report_approval():
    result = validate_report(
        {
            "metadata": {
                "detected_quarter": "Q3",
                "source_format": "INTOPIA quarterly output",
            },
            "finance": {"revenue_sf": 100, "gross_profit_sf": 20, "ending_cash_sf": 50, "debt_sf": 0, "ar_sf": 0, "ap_sf": 0},
            "operations": [
                {
                    "quarter": "Q3",
                    "area": "Europe",
                    "product": "Y",
                    "model": "Standard",
                    "grade": 1,
                    "plants": 1,
                    "plant_capacity": 35_000,
                    "actual_production": 30_000,
                    "actual_sales": 25_000,
                    "ending_inventory": 5_000,
                }
            ],
            "validation": [
                {
                    "code": "balance_reconciliation",
                    "status": "error",
                    "message": "Consolidated balance difference: 500 SF.",
                }
            ],
        },
        "Q3",
    )

    assert result["status"] == "blocked"
    check = next(item for item in result["checks"] if item["rule_id"] == "REPORT-BALANCE_RECONCILIATION")
    assert check["blocking"] is True
    assert check["status"] == "fail"


def test_exact_quarterly_report_requires_finance_and_operations():
    result = validate_report(
        {
            "metadata": {
                "detected_quarter": "Q3",
                "source_format": "INTOPIA quarterly output",
            },
            "finance": {},
            "operations": [],
        },
        "Q3",
    )

    rule_ids = {item["rule_id"] for item in result["blocking_issues"]}
    assert {"REPORT-MISSING-FINANCE", "REPORT-MISSING-OPERATIONS"} <= rule_ids


def test_scorecard_uses_consolidated_assets_and_equity_not_regional_control_accounts():
    consolidated = {
        "inventory_value_sf": 2_251_199,
        "current_assets_sf": 3_318_651,
        "current_liabilities_sf": 2_144_512,
        "total_assets_sf": 8_358_651,
        "total_liabilities_sf": 2_787_945,
        "equity_sf": 5_570_707,
    }
    finance = [
        {
            "quarter": "Q3",
            "revenue_sf": 613_053,
            "net_profit_sf": -499_768,
            "notes": f"Official actual [[BALANCE:{json.dumps(consolidated, separators=(',', ':'))}]]",
        }
    ]
    regional = [
        {"quarter": "Q3", "area": "Europe", "equity_lc": 3_717_001, "total_investment_lc": 4_860_800, "fx_to_sf": 1.0},
        {"quarter": "Q3", "area": "Brazil", "equity_lc": 2_085_616, "total_investment_lc": 2_094_904, "fx_to_sf": 0.5},
        {"quarter": "Q3", "area": "Liechtenstein", "equity_lc": 6_162_397, "total_investment_lc": 7_230_000, "fx_to_sf": 1.0},
    ]

    result = build_scorecard("Q3", finance, [], regional)

    assert result["past"]["values"]["roe"] == pytest.approx(-499_768 / 5_570_707)
    assert result["past"]["values"]["roi"] == pytest.approx(-499_768 / 8_358_651)
