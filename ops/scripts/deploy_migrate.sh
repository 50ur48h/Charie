#!/usr/bin/env sh
# Run `alembic upgrade head` against the deployed platform database (WP12.2).

set -eu

: "${RESOURCE_GROUP:?RESOURCE_GROUP is not set}"
: "${REGISTRY:?REGISTRY is not set; it comes from the infra deployment outputs}"
: "${IMAGE_TAG:?IMAGE_TAG is not set}"

JOB_NAME="${MIGRATE_JOB_NAME:-cj-charie-migrate-dev}"

# Print why the job failed, and get this right.
dump_logs() {
  execution=$1
  echo "--- container output for $execution ---" >&2
  if az containerapp job logs show \
    --name "$JOB_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --container migrate \
    --execution "$execution" \
    --tail 200 >&2 2>/dev/null; then
    return 0
  fi

  echo "The replica is gone, so live logs are unavailable. Querying Log Analytics." >&2
  # Installed explicitly rather than left to az's dynamic install.
  az extension add --name log-analytics --allow-preview true --only-show-errors >/dev/null 2>&1 || true
  workspace=$(az monitor log-analytics workspace show \
    --resource-group "$RESOURCE_GROUP" \
    --name "${LOG_WORKSPACE:-log-charie-dev}" \
    --query customerId -o tsv 2>/dev/null || true)
  if [ -z "$workspace" ]; then
    echo "No Log Analytics workspace found; the reason is not recoverable here." >&2
    return 0
  fi

  az monitor log-analytics query \
    --workspace "$workspace" \
    --analytics-query "ContainerAppConsoleLogs | where ContainerName == 'migrate' | order by TimeGenerated asc | project TimeGenerated, Log | take 200" \
    -o tsv >&2 2>/dev/null ||
    echo "The query failed; the az extension 'log-analytics' may not be installed." >&2

  echo >&2
  echo "If the output above is empty the logs have not arrived yet rather than" >&2
  echo "not existing: console logs can take ~15 minutes to reach Log Analytics." >&2
  echo "Re-run that query then, before changing anything." >&2
}

echo "Starting $JOB_NAME on ${REGISTRY}/charie-api:${IMAGE_TAG}"

# Point the job at the image this deploy built, then start it.
az containerapp job update \
  --name "$JOB_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --image "${REGISTRY}/charie-api:${IMAGE_TAG}" \
  --output none

EXECUTION=$(az containerapp job start \
  --name "$JOB_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query name -o tsv)

echo "Execution $EXECUTION started; waiting for it to finish."

# Wait, and fail on anything that is not Succeeded.
i=0
while [ "$i" -lt 60 ]; do
  STATUS=$(az containerapp job execution show \
    --name "$JOB_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --job-execution-name "$EXECUTION" \
    --query properties.status -o tsv 2>/dev/null || echo Unknown)
  case "$STATUS" in
  Succeeded)
    echo "Migration succeeded."
    exit 0
    ;;
  Failed | Cancelled)
    echo "Migration $STATUS. The deploy stops here — the app is still on the" >&2
    echo "previous revision, which matches the previous schema." >&2
    dump_logs "$EXECUTION"
    exit 1
    ;;
  *)
    i=$((i + 1))
    sleep 10
    ;;
  esac
done

echo "Migration did not finish within ten minutes; refusing to swap the" >&2
echo "revision. Its last status was '$STATUS'." >&2
exit 1
