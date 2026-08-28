# Deployment

This directory contains Kubernetes manifests for deploying canvas-outline-notes.

## Architecture

**Long-running Deployment (Recommended):**
- `deployment.yaml` - Single pod running both sync and notes on schedules
- Simpler than CronJobs, uses less resources
- State persisted in emptyDir volume (resets on pod restart, which is fine - will just re-sync)

**Legacy CronJob approach:**
- `canvas-sync-cronjob.yaml` + `canvas-outline-cronjob.yaml` - Separate cron jobs
- Requires `canvas-notes-serviceaccount.yaml` for state management
- More complex, kept for compatibility

## Configuration

1. **Create secrets:**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: canvas-secrets
  namespace: dav
stringData:
  CANVAS_ICS_URL: "https://canvas.example.edu/feeds/calendars/user_xxx.ics"
  CANVAS_API_TOKEN: "your-token-here"
  CANVAS_API_TOKEN_ISSUED_AT: "2026-01-01"
  DAV_USERNAME: "username"
  DAV_PASSWORD: "password"
  CHAT_API_KEY: "your-llm-api-key"
  OUTLINE_API_TOKEN: "your-outline-token"
```

2. **Update environment variables in deployment.yaml:**
- `CANVAS_BASE_URL` - Your Canvas instance
- `DAV_BASE_URL` - Your CalDAV server
- `CHAT_API_BASE_URL` - Your LLM API endpoint
- `OUTLINE_BASE_URL` - Your Outline instance
- `SYNC_INTERVAL_MINUTES` - How often to sync assignments (default: 15)
- `NOTES_INTERVAL_MINUTES` - How often to generate notes (default: 60)

3. **Copy scripts to ConfigMap:**
The scripts are in separate ConfigMaps for clarity:
- `canvas-sync-configmap.yaml` - CalDAV sync script
- `canvas-outline-configmap.yaml` - Note generation script

Combine them into a single ConfigMap named `canvas-scripts` or use kustomize to merge.

## Deploy

```bash
kubectl apply -f namespace.yaml
kubectl apply -f canvas-secrets.yaml  # your secrets
kubectl apply -f canvas-sync-configmap.yaml
kubectl apply -f canvas-outline-configmap.yaml
kubectl apply -f deployment.yaml
```

Or use the legacy CronJob approach:
```bash
kubectl apply -f canvas-notes-serviceaccount.yaml
kubectl apply -f canvas-sync-cronjob.yaml
kubectl apply -f canvas-outline-cronjob.yaml
```
