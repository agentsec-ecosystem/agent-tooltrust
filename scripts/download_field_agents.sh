#!/usr/bin/env bash
# Download field-test agent checkouts for the M7 field test, IN PARALLEL.
#
# Clones each upstream framework repo (gitignored under
# tests/field/agents/vendor/<repo>/) so the 100 build_agent shims have real
# agent code to import. Run from the repo root:
#
#   ./scripts/download_field_agents.sh          # all 12 repos, 4 at a time
#   ./scripts/download_field_agents.sh --jobs 8 # more parallelism
#   ./scripts/download_field_agents.sh ag2      # a single repo
#
# --depth 1 avoids full history; llama_index uses a sparse checkout (docs only)
# to avoid pulling ~1.1GB.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="$REPO_ROOT/tests/field/agents/vendor"
JOBS=4

# repo_dir|remote|commit(optional, HEAD if omitted)
REPOS=(
  "langgraph|https://github.com/langchain-ai/langgraph.git|d56666f"
  "pydantic-ai|https://github.com/pydantic/pydantic-ai.git|d995cfe"
  "crewAI-examples|https://github.com/crewAIInc/crewAI-examples.git|da94a91"
  "openai-agents-python|https://github.com/openai/openai-agents-python.git|23da2b6"
  "ag2|https://github.com/ag2ai/ag2.git|97d70e3"
  "llama_index|https://github.com/run-llama/llama_index.git|47b85c8"
  "adk-python|https://github.com/google/adk-python.git|bc2c97c"
  "sm-deepsearch|https://github.com/lwyBZss8924d/DeepSearchAgents.git|a437476"
  "sm-smolcc|https://github.com/aniemerg/smolcc.git|HEAD"
  "adk-sokart|https://github.com/sokart/adk-walkthrough.git|HEAD"
  "sm-qs|https://github.com/ababdotai/awesome-agent-quickstart.git|HEAD"
  "_awesome-quickstart|https://github.com/ababdotai/awesome-agent-quickstart.git|HEAD"
)

download_one() {
  local entry="$1"
  local dir="${entry%%|*}"
  local rest="${entry#*|}"
  local remote="${rest%%|*}"
  local commit="${rest#*|}"

  local dest="$VENDOR_DIR/$dir"
  mkdir -p "$(dirname "$dest")"

  if [ -d "$dest/.git" ]; then
    echo "[skip] $dir already cloned"
    return
  fi

  echo "[clone] $dir @ ${commit:-HEAD}"
  if [ "$dir" = "llama_index" ]; then
    git clone --depth 1 --filter=blob:none --sparse "$remote" "$dest" >/dev/null 2>&1 || \
      git clone --depth 1 "$remote" "$dest" >/dev/null 2>&1
    git -C "$dest" sparse-checkout set docs/examples/agent docs/examples/workflow >/dev/null 2>&1 || true
  else
    git clone --depth 1 "$remote" "$dest" >/dev/null 2>&1 || {
      echo "[fail] $dir: clone failed" >&2
      return
    }
  fi

  if [ "$commit" != "HEAD" ] && [ -n "$commit" ]; then
    git -C "$dest" fetch --depth 1 origin "$commit" >/dev/null 2>&1 || true
    git -C "$dest" checkout "$commit" --detach >/dev/null 2>&1 || true
  fi
  echo "[done] $dir -> $(git -C "$dest" rev-parse --short HEAD)"
}
export -f download_one
export VENDOR_DIR

if [ -n "${1:-}" ] && [ "$1" != "--jobs" ]; then
  download_one "$1"
  exit 0
fi

if [ "${1:-}" = "--jobs" ]; then
  JOBS="${2:-4}"
  shift 2 || true
fi

echo "Downloading ${#REPOS[@]} repos with $JOBS parallel jobs..."
printf '%s\n' "${REPOS[@]}" | xargs -P "$JOBS" -I{} bash -c 'download_one "$1"' _ {}

echo
echo "Done. Vendor checkout sizes:"
du -sh "$VENDOR_DIR"/* 2>/dev/null || true