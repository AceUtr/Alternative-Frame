import json
from pathlib import Path

from validate_contribution import MANIFESTS, parse_args
from validation.runner import ContributionValidator


ROOT = Path(__file__).parents[1]


def test_all_cli_targets_have_valid_manifests():
    assert set(MANIFESTS) == {
        ("domain", "software"),
        ("domain", "research"),
        ("runtime", "edge-cloud"),
        ("module", "evaluation"),
    }
    for filename in MANIFESTS.values():
        payload = json.loads((ROOT / "validation/manifests" / filename).read_text(encoding="utf-8"))
        ContributionValidator._validate_manifest(payload)
        assert payload["required_files"]
        assert payload["test_commands"]
        assert payload["scan_paths"]


def test_cli_selector_and_skip_smoke_are_parsed():
    args = parse_args(["--domain", "research", "--skip-smoke"])
    assert args.domain == "research"
    assert args.skip_smoke is True


def test_redaction_removes_keys_and_personal_paths():
    raw = "api_key='abcdefghijklmnop1234' C:\\Users\\alice\\project Bearer abcdefghijklmnop"
    sanitized = ContributionValidator._redact(raw)
    assert "abcdefghijklmnop1234" not in sanitized
    assert "alice" not in sanitized
    assert "Bearer abcdefghijklmnop" not in sanitized


def test_compact_limits_multiline_command_output():
    compact = ContributionValidator._compact("first\n" + "x" * 100, limit=30)
    assert "\n" not in compact
    assert len(compact) == 30
    assert compact.endswith("...")
