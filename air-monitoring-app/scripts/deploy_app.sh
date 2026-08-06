#!/bin/bash
# =============================================================
# deploy_app.sh - Full CI/CD deploy for Air Monitoring App
# Usage: ./scripts/deploy_app.sh <TARGET>
#   TARGET: D (dev), T (test), A (acc), P (prd)
#
# Auto-detection: If TARGET is not provided, detects from DATABRICKS_HOST.
#
# What this script does:
#   1. Auto-detects target from DATABRICKS_HOST (if not provided)
#   2. Swaps env-specific app.yaml BEFORE bundle deploy
#   3. Runs `databricks bundle deploy --target <TARGET>`
#   4. Restores original app.yaml in local git (no dirty state)
#   5. Triggers `databricks apps deploy` to redeploy the app
#
# CI/CD Integration:
#   - Azure DevOps / GitHub Actions just calls: ./scripts/deploy_app.sh
#   - DATABRICKS_HOST must be set (auto-detection works from it)
#   - Auth (SPN token or OIDC) must be configured in env
#
# NOTE: The app already exists on ACC/PRD (created via UI/Git).
#       We do NOT manage it as a DAB resource (causes ALREADY_EXISTS).
# =============================================================
set -euo pipefail

APP_NAME="air-monitoring-app"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SRC_DIR="$PROJECT_DIR/src"

# ─── Auto-detect target from DATABRICKS_HOST if not provided ───
TARGET="${1:-}"
if [[ -z "$TARGET" ]]; then
  HOST="${DATABRICKS_HOST:-}"
  if [[ -z "$HOST" ]]; then
    echo "ERROR: No TARGET argument and DATABRICKS_HOST not set."
    echo "Usage: $0 <D|T|A|P>  (or set DATABRICKS_HOST for auto-detection)"
    exit 1
  fi
  if [[ "$HOST" == *"4796304964978539"* ]]; then
    TARGET="A"
  elif [[ "$HOST" == *"4844910598668398"* ]]; then
    TARGET="P"
  elif [[ "$HOST" == *"7181820732839861"* ]]; then
    TARGET="D"
  else
    echo "ERROR: Cannot auto-detect target from DATABRICKS_HOST=$HOST"
    echo "Known workspaces: 7181820732839861 (D/T), 4796304964978539 (A), 4844910598668398 (P)"
    exit 1
  fi
  echo "Auto-detected target: $TARGET (from DATABRICKS_HOST)"
fi

# ─── Map target -> workspace source path and env yaml ───
case "$TARGET" in
  D)
    WORKSPACE_SRC="/Workspace/Users/${DEPLOYER_USER:-$USER}/ds-air-monitoring-app/D/files/src"
    ENV_YAML="app.yaml"
    ;;
  T)
    WORKSPACE_SRC="/Workspace/automation/ds-air-monitoring-app/T/files/src"
    ENV_YAML="app.yaml"
    ;;
  A)
    WORKSPACE_SRC="/Workspace/automation/ds-air-monitoring-app/A/files/src"
    ENV_YAML="app.acc.yaml"
    ;;
  P)
    WORKSPACE_SRC="/Workspace/automation/ds-air-monitoring-app/P/files/src"
    ENV_YAML="app.prd.yaml"
    ;;
  *)
    echo "ERROR: Unknown target '$TARGET'. Use D, T, A, or P."
    exit 1
    ;;
esac

echo "========================================"
echo "Deploying Air Monitoring App (CI/CD)"
echo "  Target:        $TARGET"
echo "  Env YAML:      $ENV_YAML"
echo "  Workspace src: $WORKSPACE_SRC"
echo "  Host:          ${DATABRICKS_HOST:-not set}"
echo "========================================"

# ─── Step 1: Swap env-specific yaml → app.yaml BEFORE bundle deploy ───
ORIGINAL_YAML=""
if [[ "$ENV_YAML" != "app.yaml" ]]; then
  echo "[1/4] Swapping $ENV_YAML → app.yaml (local, pre-deploy)..."
  ORIGINAL_YAML="$SRC_DIR/app.yaml"
  cp "$SRC_DIR/app.yaml" "$SRC_DIR/app.yaml.bak"
  cp "$SRC_DIR/$ENV_YAML" "$SRC_DIR/app.yaml"
else
  echo "[1/4] Using default app.yaml (correct for $TARGET)."
fi

# ─── Step 2: Bundle deploy (uploads correct app.yaml to workspace) ───
echo "[2/4] Running databricks bundle deploy --target $TARGET..."
databricks bundle deploy --target "$TARGET"

# ─── Step 3: Restore original app.yaml (keep git clean) ───
if [[ -n "$ORIGINAL_YAML" && -f "$SRC_DIR/app.yaml.bak" ]]; then
  echo "[3/4] Restoring original app.yaml (git clean)..."
  mv "$SRC_DIR/app.yaml.bak" "$SRC_DIR/app.yaml"
else
  echo "[3/4] No restore needed."
fi

# ─── Step 4: Deploy the app (triggers build + restart) ───
echo "[4/4] Deploying app to compute..."
databricks apps deploy "$APP_NAME" \
  --source-code-path "$WORKSPACE_SRC"

echo "========================================"
echo "SUCCESS: App deployed for target $TARGET"
echo "  App URL: ${DATABRICKS_HOST:-}/apps/$APP_NAME"
echo "========================================"
