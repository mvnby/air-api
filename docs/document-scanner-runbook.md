# Private document scanner

NL runs the ClamAV daemon and signature updater. BY connects to NL over the existing WireGuard mesh with mutual TLS and exact peer-certificate pins. ClamAV has no network interface. The relay listens only on the NL WireGuard IP and accepts the BY certificate. The API uses a local Unix socket on either node.

| Host | API socket on the host | Relay |
| --- | --- | --- |
| NL | `/opt/air-api/document-scanner/clamd.sock` | WireGuard address `10.77.0.2:3311` to the ClamAV socket |
| BY | `/opt/mvn-reserve/document-scanner/clamd.sock` | Local socket to `10.77.0.2:3311` |

The scanner accepts streams up to 10 MiB for external order documents. If either daemon or the tunnel is unavailable, the production application must reject new uploads before storage. The document scanner is separate from the Belzakupki attachment pipeline.

## Install the host services

1. Prove both authorized SSH identities and the live Patroni topology using the [API HA runbook](api-ha-runbook.md). Check NL has memory for the scanner and a normal blue-green release. Use the distro `stunnel4` package on both nodes. Pull the reviewed immutable ClamAV image from [the scanner Compose file](../deploy/ha/document-scanner/compose.yml) on NL.
2. Stage the [scanner assets](../deploy/ha/document-scanner) on each host in a root-owned directory and run `bash prepare-host.sh nl` on NL and `bash prepare-host.sh by` on BY. The script creates endpoint keys only when both local files are absent. Keys stay on the hosts. The relay sees the socket directory through its systemd mount namespace, so the permissions of the application project directory stay intact.
3. Through the pinned SSH paths, exchange only `/etc/mvn-document-scanner/tls/local.pem`. On each host install the verified certificate of the other host as `/etc/mvn-document-scanner/tls/peer.pem`, owner `root:mvn-docscan`, mode `0640`. Verify the subject, expiry, identity fingerprint and TLS server or client certificate purpose before installing the pin.
4. On NL run `cd /opt/mvn-document-scanner` and `docker compose -p mvn-document-scanner up -d freshclam`. Check the first signature update succeeds, then run `docker compose -p mvn-document-scanner up -d clamd`. `freshclam` checks for updates automatically. `clamd` reloads the shared signature database. The updater alone has outbound networking.
5. Enable `mvn-document-scanner-relay.service` on NL, then BY. Verify the host Unix sockets have mode `0660`. Verify the only TCP listener for the relay is `10.77.0.2:3311` on NL. Check from BY that a connection without the pinned client certificate cannot obtain a ClamAV response.
6. Scan a clean fixture and the standard EICAR test file through each host Unix socket. Before application cutover, briefly stop the NL relay and show that the BY client gets no clean verdict. Start the relay again and repeat the clean check. Verify `/api/ready` and that NL stays above deploy memory requirements.

## Connect the application

Keep the host services independent from the attested Patroni Compose deployment. Use the reviewed socket-mount release and the [atomic PITR procedure](api-ha-runbook.md#postgresql-pitr) for any change to those Compose files. Once both sockets are mounted at `/run/mvn-document-scanner/clamd.sock`, set `EXTERNAL_DOCUMENT_CLAMD_UNIX_SOCKET` to that path and run the clean verdict probe in the exact staged application image on both hosts. Then check a clean upload and rejection when the scanner is unavailable through the application path.

## Maintain or roll back

Check the updater logs and the loaded database version when troubleshooting. Renew endpoint certificates before expiry. Prepare and verify the new pins over SSH before changing the active endpoint keys, then restart the relays during a planned upload pause. Keep public and old leaf certificates only as long as needed to verify the rotation. Keep private keys out of Git and out of transfer bundles.

Before API cutover, `systemctl disable --now mvn-document-scanner-relay.service` on both hosts and `docker compose -p mvn-document-scanner stop` in `/opt/mvn-document-scanner` on NL stop the scanner path. The signature volume is retained. After cutover, use the normal application rollback procedure and preserve the attested Compose mounts. An unavailable scanner continues to reject new uploads.
