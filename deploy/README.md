# Kubernetes Deployment

The scripts are baked into the image — no ConfigMaps needed.

## Quick start

```bash
# 1. Apply PVC (once, before anything else)
kubectl apply -f pvc.yaml

# 2. Apply RBAC (ServiceAccount for token updater)
kubectl apply -f canvas-notes-serviceaccount.yaml

# 3. Create secrets (see canvas-outline-secret.example.yaml)
kubectl create secret generic canvas-sync-secrets -n dav \
  --from-literal=CANVAS_ICS_URL=... \
  --from-literal=DAV_USERNAME=... \
  --from-literal=DAV_PASSWORD=...

kubectl create secret generic canvas-outline-secrets -n dav \
  --from-literal=CHAT_API_KEY=... \
  --from-literal=OUTLINE_API_TOKEN=...

# 4. Deploy CronJobs + token updater
kubectl apply -f canvas-sync-cronjob.yaml
kubectl apply -f canvas-notes-cronjob.yaml
kubectl apply -f token-updater-deployment.yaml
```

## Files

| File | Purpose |
|------|---------|
| `pvc.yaml` | Shared storage for state file and token file |
| `canvas-notes-serviceaccount.yaml` | RBAC for token updater to patch secrets |
| `canvas-sync-cronjob.yaml` | Syncs Canvas → CalDAV every 15 min |
| `canvas-notes-cronjob.yaml` | Generates AI study notes every hour |
| `token-updater-deployment.yaml` | Web form for rotating Canvas API token |

## Triggering manually

```bash
# Run sync now
kubectl create job -n dav canvas-sync-manual --from=cronjob/canvas-sync

# Run notes now
kubectl create job -n dav canvas-notes-manual --from=cronjob/canvas-notes

# View logs
kubectl logs -n dav job/canvas-sync-manual
kubectl logs -n dav job/canvas-notes-manual
```

## Token updater

Expose the token updater behind your auth proxy (e.g. Authentik forward-auth).
It auto-detects Kubernetes and patches `canvas-sync-secrets` directly.
No manual `kubectl` needed to rotate the 90-day Canvas token.
