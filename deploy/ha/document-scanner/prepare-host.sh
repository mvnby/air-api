#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 1 || $(id -u) != 0 ]]; then
  echo 'Usage as root: prepare-host.sh nl|by' >&2
  exit 2
fi
case "$1" in
  nl) project=/opt/air-api; usage=serverAuth ;;
  by) project=/opt/mvn-reserve; usage=clientAuth ;;
  *) echo 'Expected host role nl or by' >&2; exit 2 ;;
esac

source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
config_dir=/etc/mvn-document-scanner
runtime_dir=/opt/mvn-document-scanner
account=mvn-docscan

[[ -d "$project" && -x /usr/bin/stunnel4 ]]
if ! getent passwd "$account" >/dev/null; then
  useradd --system --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin "$account"
fi
[[ $(id -gn "$account") == "$account" ]]
[[ $(getent passwd "$account" | cut -d: -f7) == /usr/sbin/nologin ]]

for directory in "$config_dir" "$config_dir/tls" "$project/document-scanner" "$runtime_dir"; do
  [[ ! -L "$directory" ]]
done
install -d -o root -g "$account" -m 0750 "$config_dir" "$config_dir/tls"
install -d -o "$account" -g "$account" -m 0750 "$project/document-scanner"
install -o root -g "$account" -m 0640 "$source_dir/stunnel-$1.conf" "$config_dir/stunnel.conf"
install -o root -g root -m 0644 "$source_dir/mvn-document-scanner-relay.service" /etc/systemd/system/
install -d -o root -g root -m 0755 /etc/systemd/system/mvn-document-scanner-relay.service.d
# Mount only the socket directory into the service namespace and preserve the
# permissions of the application project directory.
printf '[Service]\nBindPaths=%s/document-scanner:/run/mvn-document-scanner\n' "$project" \
  > /etc/systemd/system/mvn-document-scanner-relay.service.d/socket.conf

if [[ ! -e "$config_dir/tls/local.pem" && ! -e "$config_dir/tls/local.key" ]]; then
  umask 077
  candidate=$(mktemp -d "$config_dir/tls/keygen.XXXXXX")
  trap 'rm -f "$candidate/local.pem" "$candidate/local.key"; rmdir "$candidate"' EXIT
  openssl req -new -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
    -noenc -sha256 -days 365 -subj "/CN=mvn-docscan-$1" \
    -addext 'basicConstraints=critical,CA:FALSE' -addext 'keyUsage=critical,digitalSignature' \
    -addext "extendedKeyUsage=$usage" \
    -keyout "$candidate/local.key" -out "$candidate/local.pem"
  install -o root -g "$account" -m 0640 "$candidate/local.key" "$config_dir/tls/local.key"
  install -o root -g "$account" -m 0640 "$candidate/local.pem" "$config_dir/tls/local.pem"
fi
for credential in local.pem local.key; do
  [[ ! -L "$config_dir/tls/$credential" && -s "$config_dir/tls/$credential" ]]
done
openssl x509 -in "$config_dir/tls/local.pem" -noout -checkend 86400 >/dev/null

if [[ $1 == nl ]]; then
  install -d -o root -g root -m 0755 "$runtime_dir"
  install -o root -g root -m 0644 "$source_dir/compose.yml" "$source_dir/clamd.conf" \
    "$source_dir/freshclam.conf" "$runtime_dir/"
  umask 077
  printf 'DOCSCAN_UID=%s\nDOCSCAN_GID=%s\n' "$(id -u "$account")" "$(id -g "$account")" > "$runtime_dir/.env.new"
  mv -T "$runtime_dir/.env.new" "$runtime_dir/.env"
  docker compose -f "$runtime_dir/compose.yml" config --quiet
fi
systemd-analyze verify /etc/systemd/system/mvn-document-scanner-relay.service
systemctl daemon-reload
