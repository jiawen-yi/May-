import json
import subprocess
import sys
from pathlib import Path

from may_trade.cli import main
from may_trade.config import load_settings
from may_trade.fixture import load_scan_fixture
from may_trade.pipeline import scan

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "tests" / "fixtures" / "sample_plan.json"
FAIL = ROOT / "tests" / "fixtures" / "rr_fail.json"
UNIVERSE = ROOT / "tests" / "fixtures" / "sample_universe.json"


def test_evaluate_fixture_prints_pass_and_json_intent(capsys):
    assert main(["evaluate", "--fixture", str(SAMPLE)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "PASS"
    payload = json.loads("\n".join(lines[1:]))
    assert payload["decision"] == "PASS"
    assert payload["dry_run"] is True
    assert [item["intent_type"] for item in payload["intents"]] == ["entry", "oco"]
    assert payload["intents"][0]["order_type"] == "limit"
    assert payload["intents"][1]["legs"][0]["kind"] == "stop"


def test_evaluate_rr_fixture_prints_fail(capsys):
    assert main(["evaluate", "--fixture", str(FAIL)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "FAIL"
    payload = json.loads("\n".join(lines[1:]))
    assert payload["intents"] == []
    assert any(item["code"] == "rr_below_min" for item in payload["reasons"])


def test_module_entrypoint_matches_the_library():
    completed = subprocess.run(
        [sys.executable, "-m", "may_trade.cli", "evaluate", "--fixture", str(SAMPLE)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert completed.stdout.splitlines()[0] == "PASS"
    payload = json.loads("\n".join(completed.stdout.splitlines()[1:]))
    assert payload["symbol"] == "ANET"
    assert payload["intents"][1]["intent_type"] == "oco"


def test_scan_sorts_leaders_first_and_stands_down_a_full_chain():
    candidates, account, unlock, as_of = load_scan_fixture(UNIVERSE)
    result = scan(candidates, account, unlock=unlock, as_of=as_of)
    assert [item.symbol for item in result.ranked] == ["SMCI", "ANET"]
    assert result.ranked[0].decision.value == "FAIL"
    assert result.ranked[1].decision.value == "PASS"
    assert result.ranked[1].sector_lagging is True
    assert result.stood_down == [{"symbol": "AMD", "chain": "memory", "reason": "chain_full"}]


def test_scan_cli_emits_json(capsys):
    assert main(["scan", "--fixture", str(UNIVERSE)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["note"] == "sector_rank_is_sort_only"
    assert payload["ranked"][1]["decision"] == "PASS"


def test_route_without_live_does_not_submit(capsys):
    assert main(["route", "--fixture", str(SAMPLE)]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "DRY_RUN"


def test_route_live_without_env_is_refused(capsys, monkeypatch):
    monkeypatch.delenv("MAY_LIVE_TRADING", raising=False)
    code = main(["route", "--fixture", str(SAMPLE), "--live", "--broker", "paper"])
    assert code == 2
    assert "MAY_LIVE_TRADING" in capsys.readouterr().err


def test_route_live_paper_records_and_schwab_stays_a_stub(capsys, monkeypatch):
    monkeypatch.setenv("MAY_LIVE_TRADING", "1")
    assert main(["route", "--fixture", str(SAMPLE), "--live", "--broker", "paper"]) == 0
    paper_out = capsys.readouterr().out
    assert paper_out.splitlines()[0] == "ROUTED"
    assert json.loads("\n".join(paper_out.splitlines()[1:]))["receipts"][1]["intent_type"] == "oco"

    assert main(["route", "--fixture", str(SAMPLE), "--live", "--broker", "schwab"]) == 3
    assert "Schwab web UI" in capsys.readouterr().err


def test_example_config_loads_at_the_principle_ceilings():
    settings = load_settings(ROOT / "config.example.yaml")
    assert settings.rr_min == 2.0
    assert settings.stack_risk_max_pct == 0.03
    assert settings.day_loss_halt_pct == 0.015
    assert settings.duration_risk_caps["swing_1_2"] == 0.015
    assert settings.wash_rebuy_notional_cap == 150
