# CaptureCare Deployment Guide

## ⚠️ IMPORTANT: Project Configuration

**ALWAYS deploy to this project:**
- **Project ID:** `capturecare-461801`
- **Project Number:** `310697189983`
- **Region:** `australia-southeast2`

## Service URL

The production service is available at:
```
https://capturecare-310697189983.australia-southeast2.run.app
```

## Database

- **Database Instance:** `capturecare-db`
- **Location:** `australia-southeast2-a`
- **Project:** `capturecare-461801` ✅

## Deployment Command

**ALWAYS use this command:**
```bash
gcloud run deploy capturecare \
  --source . \
  --region australia-southeast2 \
  --project capturecare-461801
```

## Setting Default Project

To avoid confusion, set the default project:
```bash
gcloud config set project capturecare-461801
```

## OAuth & API Configuration

- **Google OAuth:** Project `capturecare-461801`
- **Withings:** Uses redirect URI from `capturecare-461801`
- **All secrets:** Stored in Secret Manager for `capturecare-461801`

## ⚠️ DO NOT USE

- ❌ Project: `mystic-cable-221402` (project number: 112225034072)
- ❌ URL: `https://capturecare-3ecstuprbq-km.a.run.app`

These are from the wrong project and should not be used.
