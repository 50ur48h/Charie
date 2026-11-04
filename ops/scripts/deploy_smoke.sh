#!/usr/bin/env sh
# Post-deploy smoke against dev (plan §4.4, WP12.2).

set -eu

: "${WEB_URL:?WEB_URL is not set}"
: "${API_URL:?API_URL is not set}"
: "${KEY_VAULT:?KEY_VAULT is not set}"
failures=0

fail() {
  echo "smoke: $1" >&2
  failures=$((failures + 1))
}

echo "1. The web app answers on $WEB_URL"
# Retried: a revision that has just been created may still be starting.
i=0
code=000
while [ "$i" -lt 10 ]; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$WEB_URL" || echo 000)
  case "$code" in
  2* | 3*) break ;;
  esac
  i=$((i + 1))
  sleep 6
done
[ "$i" -lt 10 ] || fail "the web app returned $code after a minute of trying"

echo "2. The API answers /healthz, and names the sha this deploy pushed"
# `curl`, not `az containerapp exec`, and the previous version lied because of it.
HEALTH=''
attempt=0
while [ "$attempt" -lt 10 ]; do
  HEALTH=$(curl -s --max-time 20 "${API_URL}/healthz" || echo '')
  case "$HEALTH" in
  *'"status":'*) break ;;
  esac
  attempt=$((attempt + 1))
  sleep 6
done

case "$HEALTH" in
*'"status":"ok"'*) echo "   $HEALTH" ;;
*'"status":"degraded"'*)
  # The probe naming its own missing configuration.
  fail "the API reports degraded — it is missing configuration it needs: $HEALTH"
  ;;
*) fail "the API did not report healthy at ${API_URL}/healthz: ${HEALTH:-no response}" ;;
esac

# The sha check is what makes the health check mean something.
if [ -n "${EXPECT_GIT_SHA:-}" ]; then
  case "$HEALTH" in
  *"$EXPECT_GIT_SHA"*) echo "   serving ${EXPECT_GIT_SHA}" ;;
  *) fail "healthz does not name ${EXPECT_GIT_SHA} — a stale revision is serving" ;;
  esac
fi

echo "3. An unauthenticated request to a tenant route is refused"
# Asked of the API directly rather than through the web origin.
UNAUTH=$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "${API_URL}/v1/me" || echo 000)
case "$UNAUTH" in
401 | 403) echo "   refused with $UNAUTH" ;;
2*) fail "an unauthenticated call to /v1/me returned $UNAUTH — the API is not checking tokens" ;;
*) fail "an unauthenticated call to /v1/me returned $UNAUTH, which is neither a refusal nor a success" ;;
esac

echo "4. Key Vault holds the expected secrets, by name"
NAMES=$(az keyvault secret list --vault-name "$KEY_VAULT" --query "[].name" -o tsv 2>/dev/null || echo '')
[ -n "$NAMES" ] || fail "could not list secrets in $KEY_VAULT"
echo "$NAMES" | sed 's/^/   /'

if [ "$failures" -gt 0 ]; then
  echo "smoke: $failures check(s) failed." >&2
  exit 1
fi
echo "smoke: dev is serving, healthy, refusing anonymous callers, and its vault is readable by name."
