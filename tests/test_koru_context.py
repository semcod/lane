"""Keep optional Koru discovery and prompt enrichment deterministic."""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from nxdo import koru_context, planner
from nxdo.config import NxdoSettings


@pytest.fixture
def koru(monkeypatch):
    package = ModuleType("koruapi")
    integrations = ModuleType("koruapi.integrations")
    invoke = ModuleType("koruapi.invoke")
    integrations.list_integrations = Mock(return_value=[
        SimpleNamespace(id="planfile.tickets", title="Tickets", description="List tickets",
                        transport="python", methods=("list", "create"), tags=("planfile",),
                        cli_equivalent="planfile tickets list"),
        SimpleNamespace(id="custom.read", title="Custom", description="Read state",
                        transport="python", methods=(), tags=(), cli_equivalent=None),
    ])
    invoke.invoke_integration = Mock(side_effect=lambda name, **kwargs: (
        {"ok": True, "tickets": [{"id": str(n), "title": f"Work {n}"} for n in range(12)]}
        if name == "planfile.tickets" else {"ok": False, "report": {"failures": {"git": "missing"}}}
    ))
    for name, module in [("koruapi", package), ("koruapi.integrations", integrations), ("koruapi.invoke", invoke)]:
        monkeypatch.setitem(sys.modules, name, module)
    return integrations, invoke


def test_optional_koru_absence_does_not_query_project(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "koruapi.integrations", None)
    context = koru_context.build_koru_context(tmp_path)
    assert not context.available
    assert context.schema_text == ""
    assert context.project_state.open_tickets == []


def test_catalog_and_bounded_project_state_enrich_prompt(tmp_path, koru):
    context = koru_context.build_koru_context(tmp_path)
    assert context.available
    assert len(context.project_state.open_tickets) == 10
    assert context.project_state.doctor_issues == ["git: missing"]
    assert not context.project_state.doctor_ok
    for value in ["planfile.tickets", "CLI: planfile tickets list", "Methods: invoke",
                  "Work 4", "... and 5 more", "git: missing"]:
        assert value in context.schema_text
    assert "Work 5" not in context.schema_text
    assert koru[1].invoke_integration.call_count == 2
    assert "KORU-AWARE PLANNING MODE" in koru_context.get_koru_system_prompt_extension()


def test_catalog_only_mode_avoids_live_state_queries(tmp_path, koru):
    context = koru_context.build_koru_context(tmp_path, include_project_state=False)
    assert context.available
    assert "Open planfile tickets: none" in context.schema_text
    koru[1].invoke_integration.assert_not_called()


@pytest.mark.parametrize("response", [RuntimeError("offline"), {"ok": None}])
def test_failed_state_queries_do_not_remove_catalog(tmp_path, koru, response):
    invoke = koru[1].invoke_integration
    if isinstance(response, Exception):
        invoke.side_effect = response
    else:
        invoke.side_effect = None
        invoke.return_value = response
    context = koru_context.build_koru_context(tmp_path)
    assert context.available
    assert not context.project_state.open_tickets
    assert invoke.call_count == 2


def test_planner_passes_koru_context_to_provider_without_network(tmp_path, koru):
    provider = Mock()
    result = planner.generate_next_tasks(
        tmp_path, provider=provider, settings=NxdoSettings(_env_file=None), koru_aware=True,
    )
    assert result is provider.generate_plan.return_value
    prompt = provider.generate_plan.call_args.args[0]
    assert "planfile.tickets" in prompt
    assert "git: missing" in prompt
