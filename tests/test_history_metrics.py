"""Exercise metrics against a real, local history and unavailable Git."""

import subprocess
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from nxdo.cli import app
from nxdo.metrics import coupling, hotspots


@pytest.fixture
def history(tmp_path):
    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=tmp_path, check=True, capture_output=True, text=True,
        )

    git("init")
    hooks = tmp_path / ".git" / "test-hooks"
    hooks.mkdir()
    git("config", "core.hooksPath", str(hooks))

    def commit(author, message, files):
        for name, content in files.items():
            (tmp_path / name).write_text(content)
        git("add", ".")
        git("-c", f"user.name={author}", "-c", "user.email=tests@example.invalid",
            "commit", "-m", message)

    source = "def decision(x):\n" + "".join(
        f"    if x == {n}: return {n}\n" for n in range(12)
    )
    commit("Ada", "feature: initial modules", {"a.py": source, "b.py": "value = 1\n"})
    commit("Bob", "fix bug: repair hotfix patch resolves issue", {
        "a.py": source + "    return 0\n", "b.py": "value = 2\n",
    })
    commit("Cara", "feature: extend modules", {
        "a.py": source + "    return -1\n", "c.py": "value = 3\n",
        "README.md": "Documentation\n",
    })
    return tmp_path


def test_fix_commit_matches_many_keywords_but_is_counted_once(history, monkeypatch):
    real_run = subprocess.run
    calls = []

    def run(*args, **kwargs):
        calls.append(args[0])
        return real_run(*args, **kwargs)

    monkeypatch.setattr(hotspots.subprocess, "run", run)
    assert hotspots._get_bug_fix_commits(history, "a.py") == 1
    assert len(calls) == 1
    assert hotspots._get_bug_fix_commits(history, "c.py") == 0


def test_history_preserves_churn_authors_and_risk_density(history):
    commits, churn = hotspots._get_file_commits_with_info(history, "a.py")
    assert len(commits) == 3
    assert {author for _, author, _ in commits} == {"Ada", "Bob", "Cara"}
    assert churn == sum(amount for _, _, amount in commits)
    risks = hotspots.identify_bug_hotspots(history)
    by_path = {risk.file_path: risk for risk in risks}
    assert by_path["a.py"].bug_density == 0.33
    assert by_path["b.py"].bug_density == 0.5
    assert by_path["a.py"].author_count == 3
    assert "README.md" not in by_path
    assert len(hotspots.identify_bug_hotspots(history, top_n=1)) == 1
    assert hotspots.identify_bug_hotspots(history, files=["missing.py"]) == []


def test_bus_factor_identifies_single_author_and_shared_files(history):
    assert hotspots.calculate_bus_factor(history) == {"b.py": 2, "c.py": 1}
    critical = hotspots.get_critical_bus_factor_files(history)
    assert [(name, count) for name, count, _ in critical] == [("c.py", 1), ("b.py", 2)]
    assert critical[0][2] == ["Cara"]
    assert set(critical[1][2]) == {"Ada", "Bob"}


def test_coupling_and_clusters_follow_real_commits(history):
    pairs = coupling.collect_coupling_matrix(history, file_filter={".py"})
    by_pair = {(pair.file_a, pair.file_b): pair for pair in pairs}
    assert by_pair[("a.py", "b.py")].commits_together == 2
    assert by_pair[("a.py", "b.py")].coupling_score == 1
    assert coupling.get_coupling_clusters(pairs) == [{"a.py", "b.py", "c.py"}]
    assert coupling.collect_coupling_matrix(history, min_coupling=1.1) == []
    assert coupling.collect_coupling_matrix(history, file_filter={".js"}) == []


def test_metrics_cli_reports_actual_repository(history):
    result = CliRunner().invoke(app, ["metrics", str(history)])
    assert result.exit_code == 0, result.output
    for heading in ["Cyclomatic Complexity", "Coupling Clusters", "Bug Hotspots", "Low Bus Factor"]:
        assert heading in result.output
    assert "a.py" in result.output
    assert "1/3 commits" in result.output


@pytest.mark.parametrize("fails_by_exception", [False, True])
def test_metrics_degrade_when_git_is_unavailable(tmp_path, monkeypatch, fails_by_exception):
    def unavailable(*args, **kwargs):
        if fails_by_exception:
            raise OSError("git unavailable")
        return SimpleNamespace(returncode=128, stdout="")

    monkeypatch.setattr(subprocess, "run", unavailable)
    assert coupling.collect_coupling_matrix(tmp_path) == []
    assert hotspots._get_file_commits_with_info(tmp_path, "a.py") == ([], 0)
    assert hotspots._get_bug_fix_commits(tmp_path, "a.py") == 0
    assert hotspots.identify_bug_hotspots(tmp_path) == []
    assert hotspots.calculate_bus_factor(tmp_path) == {}
    assert hotspots.calculate_bus_factor(tmp_path, files=["a.py", "README.md"]) == {}
    assert hotspots.get_critical_bus_factor_files(tmp_path, {"a.py": 1}) == []


def test_numstat_tolerates_binary_and_malformed_entries(tmp_path, monkeypatch):
    output = "abc|Ada\n-\t-\timage.bin\ninvalid\t3\ta.py\n2\t3\ta.py\n"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=output))
    assert hotspots._get_file_commits_with_info(tmp_path, "a.py") == ([("abc", "Ada", 5)], 5)


def test_coupling_filters_generated_files_and_normalizes_pair_order(tmp_path, monkeypatch):
    monkeypatch.setattr(coupling, "_get_commits_with_files", lambda *a: [
        ["z.py", "a.py", "tests/a.py", "dist/a.py"], ["a.py", "z.py"],
    ])
    pairs = coupling.collect_coupling_matrix(tmp_path)
    assert [(p.file_a, p.file_b, p.commits_together) for p in pairs] == [("a.py", "z.py", 2)]
