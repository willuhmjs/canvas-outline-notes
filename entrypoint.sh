#!/bin/sh
set -e
# Inject homelab CA so Python's ssl module trusts *.will.net services
if [ -f /ca-cert/homelab-ca.crt ]; then
    cat /ca-cert/homelab-ca.crt >> /etc/ssl/certs/ca-certificates.crt
fi
exec python3 /scripts/notes.py
