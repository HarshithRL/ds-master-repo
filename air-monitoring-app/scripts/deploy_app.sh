#!/bin/bash
# =============================================================
# deploy_app.sh - Deploy Air Monitoring App AFTER bundle deploy
# Usage: ./scripts/deploy_app.sh <TARGET>
#   TARGET: D (dev), T (test), A (acc), P (prd)
#
# Prerequisites:
#   - `databricks bundle deploy --target <TARGET>` already ran
#     (handled by the foundations Automation_Deploy pipeline)
#   - DATABRICKS_HOST and auth (SPN) configured in env
#
# What this script does:
#   1. Copies env-specific app.yaml into the WORKSPACE source path
#      (overwrites the default app.yaml that bundle uploaded)
#   2. Triggers `databricks apps deploy` to redeploy the app
#
# NOTE: The app already exists on ACC/PRD (created via UI/Git).
#       We do NOT manage it as a DAB resource (causes ALREADY_EXISTS).
#       Bundle only uploads source files; this script triggers app deploy.
# =============================================================
set -euo pipefail

TARGET="${1:-}"
APP_NAME="air-monitoring-app"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SRC_DIR="$PROJECT_DIR/src"

if [[ -z "$TARGET" ]]; then
  echo "ERROR: Target not specified."
  echo "Usage: $0 <D|T|A|P>"
  exit 1
fi

# Map target -> workspace source path and env yaml
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
echo "Deploying Air Monitoring App"
echo "  Target:        $TARGET"
echo "  Env YAML:      $ENV_YAML"
echo "  Workspace src: $WORKSPACE_SRC"
echo "========================================"

# Step 1: Overwrite app.yaml in workspace with env-specific version
if [[ "$ENV_YAML" != "app.yaml" ]]; then
  echo "[1/2] Uploading $ENV_YAML as app.yaml to workspace..."
  databricks workspace import "$WORKSPACE_SRC/app.yaml" \
    --file "$SRC_DIR/$ENV_YAML" \
    --format AUTO \
    --overwrite
else
  echo "[1/2] Using default app.yaml (already correct for $TARGET)."
fi

# Step 2: Deploy the app (triggers build + restart on app compute)
echo "[2/2] Deploying app to compute..."
databricks apps deploy "$APP_NAME" \
  --source-code-path "$WORKSPACE_SRC"

echo "========================================"
echo "Done! App deployment triggered for target: $TARGET"
echo "  Monitor at: $DATABRICKS_HOST/apps/$APP_NAME"
echo "========================================"
