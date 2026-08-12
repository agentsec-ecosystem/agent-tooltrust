# Quickstart

Get from `pip install` to first decision in under 5 minutes.

## Install

```bash
pip install agent-tooltrust
```

## Init

```bash
tooltrust init --posture balanced
```
Creates `tooltrust.yaml` in the current directory with the balanced posture preset.

## First Decision

```bash
tooltrust evaluate --tool query_logs --action read --env staging --data internal --agent debug-bot
```

```
  Decision      ✓ ALLOW
  Criticality   low
  Reason code   allow_low_risk
  Explanation   query_logs (read) in staging on internal data is within the allow band. Proceeding.
```

## Programmatic Use

```python
from agent_tooltrust import Engine
from agent_tooltrust.policy.models import default_policy

engine = Engine(default_policy("balanced"))

result = engine.evaluate(
    tool_name="query_logs",
    action="read",
    environment="staging",
    data_class="internal",
    agent_id="debug-bot",
)
print(result.decision)    # "allow"
print(result.explanation) # "query_logs (read) in staging..."
```

## Explore

```bash
# Explain why a decision was made
tooltrust explain --tool deploy_service --action write --env production --data restricted --agent release-bot

# Output as JSON
tooltrust evaluate --tool query_logs --action read --env staging --data internal --agent debug-bot --format json

# Check policy validity
tooltrust check

# Compare against defaults
tooltrust diff

# Start MCP server
tooltrust serve --port 8000

# Query audit trail
tooltrust audit show --session <id>

# Full help
tooltrust --help
```