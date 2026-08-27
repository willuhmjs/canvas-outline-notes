#!/bin/sh
set -e

# Inject homelab CA so Python's ssl module trusts *.will.net services
if [ -f /ca-cert/homelab-ca.crt ]; then
    cat /ca-cert/homelab-ca.crt >> /etc/ssl/certs/ca-certificates.crt
fi

# The cluster intercepts hostname-based HTTPS connections (Traefik transparent proxy).
# Direct-IP connections reach the real servers, so resolve external hosts via DNS
# and pin the results in /etc/hosts so urllib connects by IP, bypassing the intercept.
for host in canvas.odu.edu chat.cs.odu.edu files.pythonhosted.org pypi.org; do
    ip=$(python3 -c "import socket; print(socket.getaddrinfo('$host', 443, type=socket.SOCK_STREAM)[0][4][0])" 2>/dev/null || true)
    if [ -n "$ip" ]; then
        echo "$ip $host" >> /etc/hosts
    fi
done

exec python3 /scripts/notes.py
