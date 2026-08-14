# Policy Packs

A **policy pack** is a shareable, self-contained unit of Agent ToolTrust
policy: a `tools.yaml` policy document plus an optional `tests.yaml` of golden
decision fixtures. Packs are deterministic — the same pack plus the same
fixtures produce the same decisions on every run, on any machine, with no LLM
in the loop (F-61, F-71).

## Layout

```
my-pack/
  tools.yaml    # policy document (version, rules, tool hiding, arg policy)
  tests.yaml    # optional golden fixtures proving the rules behave
```

## Minimum viable pack

A `tools.yaml` that only sets a version is valid:

```yaml
version: "1.0.0"
```

Everything else falls back to the posture default. `tests.yaml` is optional: a
pack without one validates fine and `pack test` reports 0 fixtures.

## Authoring rules

- Every tool in `tools:` must have a unique name — duplicates are rejected.
- A fixture in `tests.yaml` must reference a tool the engine can evaluate (an
  installed taxonomy tool). A fixture referencing any other tool — unknown, or
  declared in `tools:`. but not taxonomy-registered — fails validation loudly;
  it is **never** silently skipped. (Hiding and argument policy may still name
  custom tools in `tools:`; fixtures may not use them.)
- Fixtures fully specify every field (tool, action, environment, data_class,
  agent_id, expect). No wildcards: results must be reproducible.
- Unknown keys anywhere are rejected (`extra="forbid"`), so a typo like
  `environmet` is caught at validation, not in production.

## Validating and testing

```console
$ tooltrust pack validate my-pack/   # exits 0 if the pack is well-formed
$ tooltrust pack test my-pack/       # replays fixtures, 0 if all pass
```

`pack test` runs the fixtures through the real decision engine. Because the
engine never calls an LLM, output is byte-for-byte stable across runs.

## Publishing a pack

1. Author the pack in a directory following the layout above.
2. Run `tooltrust pack validate` and `tooltrust pack test` locally until clean.
3. Open a pull request adding your pack under this `packs/` directory.
4. The pack must pass `pack validate` and `pack test` in CI to merge.

This one-page guide is the contract for the pack format (M1 #91). Questions
about the schema should reference `src/agent_tooltrust/policy/pack.py` and
`src/agent_tooltrust/policy/schema.py`.