"""Verify auto mode dispatch and its dry-run boundary without a live provider."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from nxdo import cli, metrics
from nxdo.models import Task, TaskPlan


@pytest.fixture
def workflow(monkeypatch):
    plan = TaskPlan(project_name="demo", summary="Repair the parser", tasks=[
        Task(number=1, title="Parser tests", description="Cover malformed input"),
    ])
    generate = Mock(return_value=plan)
    sync = Mock()
    provider = Mock()
    monkeypatch.setattr(cli, "generate_next_tasks", generate)
    monkeypatch.setattr(cli, "_sync_planfile_if_requested", sync)
    monkeypatch.setattr(cli, "OpenAICompatProvider", provider)
    monkeypatch.setattr(cli, "get_settings", Mock())
    monkeypatch.setattr(metrics, "identify_bug_hotspots", Mock(return_value=[]))
    monkeypatch.setattr(metrics, "collect_file_metrics", Mock(return_value=[]))
    return plan, generate, sync, provider


@pytest.mark.parametrize("has_issues", [False, True])
def test_auto_dry_run_does_not_call_provider_or_write_tickets(tmp_path, workflow, has_issues):
    if has_issues:
        metrics.identify_bug_hotspots.return_value = [SimpleNamespace()]
        metrics.collect_file_metrics.return_value = [SimpleNamespace(cyclomatic_complexity=12)]
    result = CliRunner().invoke(cli.app, ["auto", str(tmp_path), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "would execute" in result.output
    assert ("high-complexity" if has_issues else "healthy") in result.output
    for mock in workflow[1:]:
        mock.assert_not_called()
    assert list(tmp_path.iterdir()) == []


def test_auto_syncs_the_generated_plan_and_forwards_context(tmp_path, workflow):
    plan, generate, sync, provider = workflow
    result = CliRunner().invoke(cli.app, ["auto", str(tmp_path), "--extra-context", "Parser failures"])
    assert result.exit_code == 0, result.output
    assert "1 tickets queued" in result.output
    assert generate.call_args.kwargs["extra_context"] == "Parser failures"
    assert generate.call_args.kwargs["koru_aware"] is True
    assert generate.call_args.kwargs["provider"] is provider.return_value
    sync.assert_called_once_with(plan, tmp_path.resolve(), sync_planfile=True)


def test_auto_provider_error_does_not_sync_partial_output(tmp_path, workflow):
    workflow[1].side_effect = ValueError("provider offline")
    result = CliRunner().invoke(cli.app, ["auto", str(tmp_path)])
    assert result.exit_code == 1
    assert "provider offline" in result.output
    workflow[2].assert_not_called()
