#!/usr/bin/env sh
# Ask the deployed identity whether it can do what the product needs (B-125).

set -eu

: "${RESOURCE_GROUP:?RESOURCE_GROUP is not set}"
: "${REGISTRY:?REGISTRY is not set; it comes from the infra deployment outputs}"
: "${IMAGE_TAG:?IMAGE_TAG is not set}"

JOB_NAME="${SELFCHECK_JOB_NAME:-cj-charie-selfcheck-dev}"
CONTAINER=selfcheck

# The whole value of this script is in what it prints when it fails.
dump_logs() {
  execution=$1
  echo "--- container output for $execution ---" >&2
  if az containerapp job logs show \
    --name "$JOB_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --container "$CONTAINER" \
    --execution "$execution" \
    --tail 100 >&2 2>/dev/null; then
    return 0
  fi

  echo "The replica is gone, so live logs are unavailable. Querying Log Analytics." >&2
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
    --analytics-query "ContainerAppConsoleLogs | where ContainerName == '$CONTAINER' | order by TimeGenerated asc | project TimeGenerated, Log | take 100" \
    -o tsv >&2 2>/dev/null ||
    echo "The query failed; the az extension 'log-analytics' may not be installed." >&2

  echo >&2
  echo "If the output above is empty the logs have not arrived yet rather than" >&2
  echo "not existing: console logs can take ~15 minutes to reach Log Analytics." >&2
}

echo "Starting $JOB_NAME on ${REGISTRY}/charie-api:${IMAGE_TAG}"

# Update first, then start. A job execution inherits the job's template.
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

# Four round trips to two services.
i=0
while [ "$i" -lt 18 ]; do
  STATUS=$(az containerapp job execution show \
    --name "$JOB_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --job-execution-name "$EXECUTION" \
    --query properties.status -o tsv 2>/dev/null || echo Unknown)
  case "$STATUS" in
  Succeeded)
    echo "The deployed identity can store a credential and store a result."
    dump_logs "$EXECUTION"
    exit 0
    ;;
  Failed | Cancelled)
    echo "selfcheck $STATUS. The apps are deployed and this identity cannot do" >&2
    echo "something the product needs — the output below names which permission." >&2
    dump_logs "$EXECUTION"
    exit 1
    ;;
  *)
    i=$((i + 1))
    sleep 10
    ;;
  esac
done

echo "selfcheck did not finish within three minutes; its last status was" >&2
echo "'$STATUS'. That is a hang rather than slowness — four round trips to two" >&2
echo "services do not take that long." >&2
dump_logs "$EXECUTION"
exit 1
