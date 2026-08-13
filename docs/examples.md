# Examples

Usage examples for Agent ToolTrust.

```python
from agent_tooltrust import RiskEngine

engine = RiskEngine()

# Safe read in staging
result = engine.evaluate(
    tool="query_logs",
    action="read",
    environment="staging",
    data_class="internal",
    agent_id="debug-bot",
)
assert result.decision == "allow"

# Dangerous write in production
result = engine.evaluate(
    tool="deploy_service",
    action="write",
    environment="production",
    data_class="internal",
    agent_id="release-bot",
)
assert result.decision == "escalate"

# Sensitive data access
result = engine.evaluate(
    tool="query_customer_db",
    action="read",
    environment="production",
    data_class="restricted",
    agent_id="support-bot",
)
assert result.decision == "audit"
```