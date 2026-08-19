# Agent Loop Provenance Skill

This directory contains the agent skill used by the Flowcept Code assistant adapters to capture the Declared Provenance Layer (DPL) for PROV-Agent-Loop experiments.

The Flowcept code assistant adapters can always capture the Observed Provenance Layer (OPL) from the code assistant session JSONL logs. The OPL includes structural information such as prompts, assistant responses, model calls, tool calls, command inputs and outputs, timestamps, statuses, errors, and token usage.

The DPL requires the assistant to explicitly emit provenance annotations for semantic concepts that cannot be reliably inferred from raw logs, such as objectives, plans, plan steps, loop iterations, evaluations, criteria and results, thoughts, observations, beliefs, decisions, mandates, memories, and lessons learned.

## Files

- `AGENT_LOOP_PROVENANCE_SKILL.md`: Source text for the agent skill. It is intentionally not named `SKILL.md` because this repository ignores `SKILL.md` files.
- `agents/openai.yaml`: Optional agent metadata for the skill.
- `references/flowcept-prov-agent-loop.md`: Detailed Flowcept/PROV-Agent-Loop mapping used by the skill.

## Using the Codex Adapter

### Installing for Codex

Codex expects installed skills to contain a file named `SKILL.md`. To install this skill locally, copy this directory into your Codex skills directory and rename the source file to `SKILL.md` in the installed copy:

```bash
mkdir -p ~/.codex/skills/agent-loop-provenance
cp AGENT_LOOP_PROVENANCE_SKILL.md ~/.codex/skills/agent-loop-provenance/SKILL.md
cp -R agents references ~/.codex/skills/agent-loop-provenance/
```

Start a new Codex session after installing or updating the skill.

### Configuring the Codex Adapter

Configure Flowcept to use the Codex adapter and point it to the Codex session JSONL file:

```yaml
adapters:
  codex:
    kind: codex
    file_path: /path/to/codex/session.jsonl
    watch_interval_sec: 1
    recursive: true
    include_developer_messages: true
    include_reasoning: true
    declared_provenance_enabled: true
```

Set `declared_provenance_enabled: true` for DPL runs. Set it to `false` for OPL-only runs.

In the Codex session used to perform the experiment, enable or invoke the `agent-loop-provenance` skill before asking the assistant to configure and run the workflow. The adapter parses the skill's `<flowcept_event>...</flowcept_event>` annotations from the Codex JSONL and maps them to Flowcept workflow, task, and entity records.