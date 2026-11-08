from app.modules.evaluation.report_gate import (
    EXPECTED_REASONS,
    REPORT_TAMPERS,
    run_report_gate_evaluation,
)


def test_every_tamper_is_blocked_by_its_intended_rule_and_controls_pass() -> None:
    result = run_report_gate_evaluation()

    assert result["failures"] == []
    assert result["interception_rate"] == 1.0
    assert result["false_block_rate"] == 0.0
    assert set(EXPECTED_REASONS) == set(REPORT_TAMPERS)
