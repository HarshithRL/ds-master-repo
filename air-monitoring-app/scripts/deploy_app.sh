#!/bin/bash
# =============================================================
# Deploy Air Monitoring V2 App to Databricks
# Usage: ./scripts/deploy_app.sh <env>
#   env: test | acc | prd
#
# Prerequisites:
#   - DATABRICKS_HOST and DATABRICKS_TOKEN must be set
#   - OR databricks CLI profile configured
# =============================================================

set -euo pipefail

ENV=${1:-test}
APP_NAME=${2:-air-monitoring-v2}
DEPLOY_PATH="/Workspace/automation/air-monitoring-app/${ENV}"

# Map env to config file
case $ENV in
  test) CONFIG_FILE="config/app.test.yaml" ;;
  acc)  CONFIG_FILE="config/app.acc.yaml" ;;
  prd)  CONFIG_FILE="config/app.prd.yaml" ;;
  *)    echo "ERROR: Unknown env '$ENV'. Use: test | acc | prd"; exit 1 ;;
esac

echo "========================================"
echo " Deploying Air Monitoring V2 App"
echo " Environment: $ENV"
echo " App name:    $APP_NAME"
echo " Deploy path: $DEPLOY_PATH"
echo " Config:      $CONFIG_FILE"
echo "========================================"

# Step 0: Initialize tables (idempotent — safe to run every deploy)
echo ""
echo "[0/4] Ensuring tables exist..."
case $ENV in
  test) UNITY_CATALOG="automation_d" ;;
  acc)  UNITY_CATALOG="automation_a" ;;
  prd)  UNITY_CATALOG="automation_p" ;;
esac

# Get warehouse ID from config file
WAREHOUSE_ID=$(grep -A1 'DATABRICKS_WAREHOUSE_ID' "$CONFIG_FILE" | grep 'value:' | awk -F'"' '{print $2}')

cat scripts/init_tables.sql | sed "s/\${UNITY_CATALOG}/$UNITY_CATALOG/g" | \
  databricks sql execute --warehouse-id "$WAREHOUSE_ID" --sql -
echo "      Done."

# Step 1: Upload source code to workspace
echo ""
echo "[1/4] Uploading source code to workspace..."
databricks workspace import-dir ./src "$DEPLOY_PATH" --overwrite
echo "      Done."

# Step 2: Copy environment-specific app.yaml (with secret injection)
echo ""
echo "[2/4] Applying environment config ($CONFIG_FILE)..."
# Inject secrets if provided via environment variables
if [ -n "${DOC_INTELLIGENCE_KEY:-}" ] || [ -n "${OPENAI_API_KEY:-}" ]; then
  echo "      Injecting secrets into app.yaml..."
  sed -e "s|{{DOC_INTELLIGENCE_KEY}}|${DOC_INTELLIGENCE_KEY:-}|g" \
      -e "s|{{OPENAI_API_KEY}}|${OPENAI_API_KEY:-}|g" \
      "$CONFIG_FILE" > /tmp/app.yaml
  databricks workspace import /tmp/app.yaml "$DEPLOY_PATH/app.yaml" --format AUTO --overwrite
  rm -f /tmp/app.yaml
else
  echo "      ⚠️  No secrets in env — deploying with placeholders (set in App UI)"
  databricks workspace import "$CONFIG_FILE" "$DEPLOY_PATH/app.yaml" --format AUTO --overwrite
fi
echo "      Done."

# Step 3: Deploy the app
echo ""
echo "[3/4] Deploying app..."
databricks apps deploy "$APP_NAME" --source-code-path "$DEPLOY_PATH"
echo "      Done."

# Step 4: Verify
echo ""
echo "[4/4] Verifying deployment..."
sleep 10
STATUS=$(databricks apps get "$APP_NAME" --output JSON | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('app_status', {}).get('state', 'UNKNOWN'))
")

if [ "$STATUS" = "RUNNING" ]; then
  echo "      ✅ App is RUNNING"
else
  echo "      ⚠️  App status: $STATUS (may still be starting)"
  echo "      Check: databricks apps get $APP_NAME"
fi

echo ""
echo "Deployment complete."
