#!/bin/sh
# Microsoft's ODBC driver for SQL Server (plan WP3.3, architecture Part 3).
set -eu

export DEBIAN_FRONTEND=noninteractive

# A mirror that stops answering must not hang the build. apt's defaults wait a long time and...
APT_OPTIONS="-o Acquire::Retries=3 -o Acquire::http::Timeout=15 -o Acquire::https::Timeout=15"

# shellcheck disable=SC2086 # word splitting is what passes these as flags
apt-get $APT_OPTIONS update
# shellcheck disable=SC2086
apt-get $APT_OPTIONS install --no-install-recommends -y ca-certificates curl gnupg

# --batch --yes --no-tty: on a CI runner there is no controlling terminal.
curl -fsSL https://packages.microsoft.com/keys/microsoft.asc |
	gpg --batch --yes --no-tty --dearmor -o /usr/share/keyrings/microsoft-prod.gpg

# Microsoft publishes one repository per distribution release.
. /etc/os-release
case "${ID:-}/${VERSION_ID:-}" in
debian/12) repository="debian/12" ;;
ubuntu/24.04) repository="ubuntu/24.04" ;;
ubuntu/22.04) repository="ubuntu/22.04" ;;
*)
	echo "no Microsoft ODBC repository known for ${ID:-unknown} ${VERSION_ID:-unknown}" >&2
	exit 1
	;;
esac

echo "deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/${repository}/prod ${VERSION_CODENAME} main" \
	>/etc/apt/sources.list.d/mssql-release.list

# shellcheck disable=SC2086
apt-get $APT_OPTIONS update
# ACCEPT_EULA is Microsoft's licence prompt for this driver.
# shellcheck disable=SC2086
ACCEPT_EULA=Y apt-get $APT_OPTIONS install --no-install-recommends -y msodbcsql18 unixodbc

# The tools that fetched the key are not wanted in a running image.
if [ "${KEEP_BUILD_TOOLS:-0}" != "1" ]; then
	apt-get purge -y curl gnupg
	apt-get autoremove -y
fi
rm -rf /var/lib/apt/lists/*

# Fail the build rather than the first connection.
test -f /etc/odbcinst.ini
grep -q "ODBC Driver 18 for SQL Server" /etc/odbcinst.ini
