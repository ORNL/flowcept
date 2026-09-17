"""Static checks on the Claude Code plugin's shipped assets.

Everything the plugin ships is declarative (JSON manifests, SKILL.md files,
shell shims), so these tests validate the files themselves: manifests parse,
referenced scripts exist and are executable, skills carry valid frontmatter
and cite only paths that exist in this repository, and the optional
auto-report hook stays silent unless explicitly enabled. Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "flowcept"
SKILLS = PLUGIN_ROOT / "skills"

_PATH_TOKEN = re.compile(r"`([^`]+)`")
_REPO_PATH = re.compile(r"^(?:src|tests|examples|docs|plugins)/[\w./-]+$|^pyproject\.toml$")


def _load_json(path: Path) -> dict:
    """Parse a JSON file, failing the test with a readable message on error."""
    assert path.is_file(), f"missing {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _frontmatter(skill_md: Path) -> dict[str, str]:
    """Parse the ``--- ... ---`` YAML-ish frontmatter of a SKILL.md into a dict."""
    lines = skill_md.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0].strip() == "---", f"{skill_md} does not start with frontmatter"
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    raise AssertionError(f"{skill_md} frontmatter never closes")


def _cited_repo_paths(skill_md: Path) -> list[str]:
    """Return every repo path cited in a skill."""
    out: list[str] = []
    for line in skill_md.read_text(encoding="utf-8").splitlines():
        for token in _PATH_TOKEN.findall(line):
            if _REPO_PATH.match(token):
                out.append(token)
    return out


# -- hooks ---------------------------------------------------------------------


def test_hooks_json_parses_and_scripts_are_executable():
    """Every script referenced by hooks.json exists and is executable."""
    hooks = _load_json(PLUGIN_ROOT / "hooks" / "hooks.json")["hooks"]
    commands = [h["command"] for entries in hooks.values() for entry in entries for h in entry["hooks"]]
    assert commands, "hooks.json declares no commands"
    for command in commands:
        match = re.search(r"\$\{CLAUDE_PLUGIN_ROOT\}(/[^\"]+)", command)
        assert match, f"unrecognized hook command: {command}"
        script = PLUGIN_ROOT / match.group(1).lstrip("/")
        assert script.is_file(), f"missing script for hook command: {command}"
        assert os.access(script, os.X_OK), f"not executable: {script}"


def test_hooks_json_capture_session_end_entry_untouched():
    """The original capture entry on SessionEnd is still first and unchanged."""
    hooks = _load_json(PLUGIN_ROOT / "hooks" / "hooks.json")["hooks"]
    first = hooks["SessionEnd"][0]["hooks"][0]
    assert first["command"] == '"${CLAUDE_PLUGIN_ROOT}/scripts/hook.sh" SessionEnd'
    assert first["timeout"] == 10


def test_hooks_json_autoreport_entry_added():
    """A second SessionEnd entry invokes autoreport.sh with a generous timeout."""
    hooks = _load_json(PLUGIN_ROOT / "hooks" / "hooks.json")["hooks"]
    assert len(hooks["SessionEnd"]) == 2
    auto = hooks["SessionEnd"][1]["hooks"][0]
    assert "autoreport.sh" in auto["command"]
    assert auto["timeout"] == 30


# -- manifests -------------------------------------------------------------------


def test_plugin_json_fields():
    """plugin.json parses, is at 0.2.0, and mentions the analysis surface."""
    manifest = _load_json(PLUGIN_ROOT / ".claude-plugin" / "plugin.json")
    assert manifest["name"] == "flowcept"
    assert manifest["version"] == "0.2.0"
    assert "MCP" in manifest["description"]
    assert "analy" in manifest["description"].lower()


def test_mcp_json_declares_provenance_server():
    """.mcp.json declares the flowcept-provenance stdio server via a real script."""
    manifest = _load_json(PLUGIN_ROOT / ".mcp.json")
    server = manifest["mcpServers"]["flowcept-provenance"]
    script = PLUGIN_ROOT / server["command"].replace("${CLAUDE_PLUGIN_ROOT}/", "")
    assert script.is_file() and os.access(script, os.X_OK)
    text = script.read_text(encoding="utf-8")
    assert "flowcept.agents.harness.mcp_server" in text
    assert "--transport stdio" in text


def test_mcp_server_module_runs_as_main():
    """The module the launcher invokes with -m has a __main__ guard."""
    module = REPO_ROOT / "src" / "flowcept" / "agents" / "harness" / "mcp_server.py"
    assert 'if __name__ == "__main__"' in module.read_text(encoding="utf-8")


def test_marketplace_json_fields():
    """marketplace.json parses, is at 0.2.0, and points at an existing plugin dir."""
    manifest = _load_json(REPO_ROOT / ".claude-plugin" / "marketplace.json")
    assert manifest["metadata"]["version"] == "0.2.0"
    (entry,) = [p for p in manifest["plugins"] if p["name"] == "flowcept"]
    assert (REPO_ROOT / entry["source"]).is_dir()
    assert "analy" in entry["description"].lower()


# -- skills ----------------------------------------------------------------------


@pytest.mark.parametrize("skill", ["session-provenance", "prov-analysis", "write-flowcept-plugin"])
def test_skill_frontmatter(skill):
    """Each skill has frontmatter whose name matches its directory."""
    fields = _frontmatter(SKILLS / skill / "SKILL.md")
    assert fields.get("name") == skill
    assert len(fields.get("description", "")) > 40


@pytest.mark.parametrize("skill", ["prov-analysis", "write-flowcept-plugin"])
def test_skill_cited_paths_exist(skill):
    """Every repo path a new skill cites exists."""
    cited = _cited_repo_paths(SKILLS / skill / "SKILL.md")
    assert cited, f"{skill} cites no repo paths"
    for path in cited:
        assert (REPO_ROOT / path).exists(), f"{skill} cites missing path: {path}"


def test_session_provenance_skill_intact():
    """The capture-side skill still documents the buffer location and record shapes."""
    text = (SKILLS / "session-provenance" / "SKILL.md").read_text(encoding="utf-8")
    for needle in ("buffers/<workflow_id>.jsonl", "agent_tool", "ai_model_invocation", "flowcept-harness flush"):
        assert needle in text


# -- autoreport behavior -----------------------------------------------------------


def test_autoreport_silent_noop_when_disabled():
    """With FLOWCEPT_HARNESS_AUTOREPORT unset, autoreport.sh exits 0 with no stdout."""
    env = {k: v for k, v in os.environ.items() if k != "FLOWCEPT_HARNESS_AUTOREPORT"}
    result = subprocess.run(
        [str(PLUGIN_ROOT / "scripts" / "autoreport.sh")],
        input=json.dumps({"hook_event_name": "SessionEnd", "session_id": "fake"}).encode(),
        capture_output=True,
        env=env,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == b""
