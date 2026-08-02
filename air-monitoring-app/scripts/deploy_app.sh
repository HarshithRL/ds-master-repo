#!/bin/bash
# =============================================================
# deploy_app.sh — Deploy Air Monitoring App to target environment
# Usage: ./scripts/deploy_app.sh <TARGET>
#   TARGET: D (dev), T (test), A (acc), P (prd)
#
# What it does:
#   1. Copies the env-specific app.yaml (app.acc.yaml / app.prd.yaml) → src/app.yaml
#   2. Runs `databricks bundle deploy --target <TARGET>` to upload source + register app
#   3. Triggers `databricks apps deploy` to actually deploy to compute
#   4. Restores src/app.yaml to the DEV default (clean git state)
# =============================================================
set -euo pipefail

TARGET="${1:-}"
APP_NAME="air-monitoring-app"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SRC_DIR="$PROJECT_DIR/src"

# Validate target
if [[ -z "$TARGET" ]]; then
  echo "ERROR: Target not specified."
  echo "Usage: $0 <D|T|A|P>"
  exit 1
fi

# Map target → env-specific yaml
case "$TARGET" in
  D|T)
    ENV_YAML="$SRC_DIR/app.yaml"  # DEV/TEST uses the default app.yaml directly
    SKIP_COPY=true
    ;;
  A)
    ENV_YAML="$SRC_DIR/app.acc.yaml"
    SKIP_COPY=false
    ;;
  P)
    ENV_YAML="$SRC_DIR/app.prd.yaml"
    SKIP_COPY=false
    ;;
  *)
    echo "ERROR: Unknown target '$TARGET'. Use D, T, A, or P."
    exit 1
    ;;
esac

# Verify env yaml exists
if [[ "$SKIP_COPY" == "false" && ! -f "$ENV_YAML" ]]; then
  echo "ERROR: Environment yaml not found: $ENV_YAML"
  exit 1
fi

echo "========================================"
echo "Deploying Air Monitoring App"
echo "  Target:   $TARGET"
echo "  Env YAML: $ENV_YAML"
echo "========================================"

# Step 1: Swap app.yaml for the target environment
if [[ "$SKIP_COPY" == "false" ]]; then
  echo "[1/4] Swapping app.yaml → env-specific config..."
  cp "$SRC_DIR/app.yaml" "$SRC_DIR/app.yaml.bak"
  cp "$ENV_YAML" "$SRC_DIR/app.yaml"
else
  echo "[1/4] Using default app.yaml (DEV/TEST)..."
fi

# Step 2: Bundle deploy (uploads source + registers app resource)
echo "[2/4] Running bundle deploy --target $TARGET..."
cd "$PROJECT_DIR"
databricks bundle deploy --target "$TARGET"

# Step 3: Trigger app deployment to compute
echo "[3/4] Deploying app to compute..."
databricks apps deploy "$APP_NAME" \
  --source-code-path "/Workspace/automation/ds-air-monitoring-app/$TARGET/files/src"

# Step 4: Restore original app.yaml
if [[ "$SKIP_COPY" == "false" ]]; then
  echo "[4/4] Restoring original app.yaml..."
  mv "$SRC_DIR/app.yaml.bak" "$SRC_DIR/app.yaml"
else
  echo "[4/4] No restore needed."
fi

echo "========================================"
echo "✅ Deploy complete for target: $TARGET"
echo "   App URL: https://$APP_NAME-<workspace_id>.azuredatabricksapps.com"
echo "========================================"
