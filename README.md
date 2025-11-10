# Makistry — Setup Guide

> Welcome to Makistry! This guide will get your local environment running for both the backend (FastAPI) and the frontend (Vite + React), with Firebase Auth, GCP Firestore/Storage, and an AI model provider (AWS Bedrock/Azure OpenAI). It’s opinionated, step‑by‑step, and meant to be copy‑paste friendly.

---

## Table of Contents

* [What You’ll Build Locally](#what-youll-build-locally)
* [Repo Structure](#repo-structure)
* [Prerequisites](#prerequisites)
* [Accounts & Free Credits](#accounts--free-credits)
* [Environment Variables](#environment-variables)

  * [Backend `.env` (Python/FastAPI)](#backend-env-pythonfastapi)
  * [Frontend `.env.local` (Vite/React)](#frontend-envlocal-vitereact)
* [One-Time Cloud Setup](#one-time-cloud-setup)

  * [Firebase (Auth + Firestore App SDK)](#firebase-auth--firestore-app-sdk)
  * [Google Cloud (Firestore + Storage + Signed URLs)](#google-cloud-firestore--storage--signed-urls)
  * [Choose Your AI Provider (Pick ONE)](#choose-your-ai-provider-pick-one)
* [Local Setup & Running](#local-setup--running)

  * [Backend (FastAPI)](#backend-fastapi)
  * [Frontend (Vite + React)](#frontend-vite--react)
  * [Together (Frontend + Backend)](#together-frontend--backend)
  * [Quick Smoke Test](#quick-smoke-test)
* [How Auth Works (End-to-End)](#how-auth-works-end-to-end)
* [Branching, Commit Style, PRs](#branching-commit-style-prs)
* [Security & Secrets](#security--secrets)

---

## What You’ll Build Locally

* **Backend**: FastAPI app exposing `/api/*` (see `app/main.py`). Stores data in **Firestore** and files in **GCS**. Generates CAD using **CadQuery** and runs background export jobs.
* **Frontend**: Vite + React SPA (see `src/`). Uses **Firebase Auth** for login, talks to the backend via `axios`.
* **Auth**: Frontend obtains a **Firebase ID token**, backend verifies it with `firebase_admin`, then issues a **Makistry JWT** for subsequent API calls.
* **AI**: Pick **AWS Bedrock (Claude Sonnet)** *or* **Azure OpenAI**. You’ll use your own free credits/keys.

---

## Repo Structure

> Key paths you’ll touch most often

```
app/
  api/v1/auth_firebase.py        # Firebase → Makistry JWT exchange
  agents/                        # Brainstorm, planner, edit, code-creation (AWS/Azure)
  core/config.py                 # Loads env vars (pydantic Settings)
  llm/azure_client.py            # Azure OpenAI client factory (optional path)
  routes/                        # API routers
  services/
    storage_gcp.py               # Firestore + GCS implementation (authoritative)
    gcp_clients.py               # Firestore/Storage clients
    auth.py                      # _sign() and get_current_user()
    sandbox.py                   # CadQuery runner
  main.py                        # FastAPI entrypoint (most routes live here)

Makistry-frontend
  src/
    components/
        artifacts/
        ui/
    contexts/
    hooks/
    lib/                           # axios, token manager, api url helpers
        api/
    pages/                         # UI
    providers/
    stores/
    firebase.ts                    # Firebase SDK init + long-polling Firestore
    App.tsx, main.tsx              # SPA wiring
  package.json                     # Frontend scripts
  .env.local
  config files

requirements.txt                   # Python deps
.env                               # API keys, model definitions, etc.
package.json
GCP service account JSON
```

---

## Prerequisites

* **Python**: 3.11+ (CadQuery wheels are available for macOS/Linux)
* **Node**: 18+ (LTS) or 20+
* **npm**: 9+ (or `pnpm` if you prefer; examples use npm)
* **gcloud** CLI (optional but helpful)

> **CadQuery note (OpenCascade)**: Wheels ship bundled for macOS/Linux. On some Linuxes you may need system libs (`libgl1`, `libxrender1`, `libxext6`). If `import OCP` fails, install those via your package manager and re-run.

---

## Accounts & Free Credits

Create your **own** accounts for secrets and keys

1. **Firebase** (free): [https://console.firebase.google.com](https://console.firebase.google.com) → create project → enable **Authentication** Google OAuth. Copy web config.
2. **Google Cloud** (free tier): Create a GCP project → enable **Firestore** (Native) + **Cloud Storage** → create a **service account** and JSON key and create appropriate storage containers and buckets.
3. **AI Provider**:

   * **AWS Bedrock** (Claude Sonnet). Get a free trial, request model access in Bedrock console → create **IAM user** with programmatic access.
   * **Azure OpenAI**. Get a free trial, create an Azure OpenAI resource → get endpoint + key from model catalog.
4. (Optional) **Resend** for email: [https://resend.com](https://resend.com) → free API key.

---

## Environment Variables

All secrets live in `.env` (backend) and `.env.local` (frontend). **Never commit** these.

### Backend `.env` (Python/FastAPI)

Create a file at repo root: `.env`. The app uses GCP; other providers can be **dummy** strings if you don’t use them but the config loader still expects them.

```dotenv
# ───────── REQUIRED for backend  ─────────
# GCP / Firestore + Storage
STORAGE_BACKEND=gcp
GCP_PROJECT_ID=<your-gcp-project-id>
GCS_BUCKET=<your-gcs-bucket-name>
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/your-service-account.json
# The service account email that signs GCS V4 URLs (must match the file above OR have TokenCreator role)
SIGNING_SA_EMAIL=<service-account@<your-gcp-project>.iam.gserviceaccount.com>

# Firebase web SDK config (from your Firebase project settings)
VITE_FIREBASE_API_KEY=<your-firebase-web-api-key>
FIREBASE_API_KEY=<same-firebase-web-api-key>
VITE_FIREBASE_AUTH_DOMAIN=<your-firebase-project>.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=<your-firebase-project-id>

# Simple JWT for Makistry app tokens (dev-only secret is fine locally)
JWT_SECRET=dev-local-secret

# Resend (can be any non-empty string if you won’t send mail in dev)
RESEND_API_KEY=dev-dummy
RESEND_DOMAIN=makistry.dev

# AWS Bedrock — Claude Sonnet
AWS_REGION=<get-from-setup>
AWS_BEARER_TOKEN_BEDROCK=<your-bearer-token-for-bedrock>
AWS_ACCESS_KEY_ID=<your-aws-access-key-id>
AWS_SECRET_ACCESS_KEY=<your-aws-secret-access-key>
SONNET_MODEL_ID=us.anthropic.claude-sonnet-4-20250514-v1:0

# Azure OpenAI — GPT/O4 
AZURE_OAI_ENDPOINT=https://<your-azure-openai>.openai.azure.com
AZURE_OAI_KEY=<your-azure-openai-key>
AZURE_CODE_MODEL=o4-mini
AZURE_CODE_API_VERSION=2024-12-01-preview
AZURE_CHAT_MODEL=gpt-4.1
AZURE_CHAT_API_VERSION=2024-12-01-preview
AZURE_INTENT_MODEL=gpt-4.1-mini
AZURE_INTENT_API_VERSION=2024-12-01-preview
AZURE_BSTORM_MODEL=gpt-4.1
AZURE_BSTORM_API_VERSION=2024-12-01-preview
AZURE_BSTORM_EDIT_MODEL=gpt-4.1-mini
AZURE_BSTORM_EDIT_API_VERSION=2024-12-01-preview
AZURE_SIM_MODEL=o4-mini
AZURE_SIM_API_VERSION=2024-12-01-preview
AZURE_SIM_EDIT_MODEL=gpt-4.1-mini
AZURE_SIM_EDIT_API_VERSION=2024-12-01-preview

# ───────── Cosmos / Azure Blob — not used in GCP mode, but required by config loader.
# Put safe dummy placeholders.
COSMOS_ENDPOINT=https://example.documents.azure.com:443/
COSMOS_KEY=dummy
COSMOS_DB=makistry-db
AZURE_BLOB_ACCOUNT_NAME=dummy
AZURE_BLOB_ACCOUNT_KEY=dummy
AZURE_BLOB_CONTAINER=cad-files
```

> **Why so many?** `app/core/config.py` defines some fields as required even if unused in GCP mode. Use safe dummy values to satisfy the loader.

### Frontend `.env.local` (Vite/React)

Create `./Makistry-frontend/.env.local`.

```dotenv
VITE_API_URL=http://localhost:8000/api

# Firebase web SDK config (from your Firebase project settings)
VITE_FIREBASE_API_KEY=<your-firebase-web-api-key>
VITE_FIREBASE_AUTH_DOMAIN=<your-firebase-project>.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=<your-firebase-project-id>
```

---

## One-Time Cloud Setup

### Firebase (Auth + Firestore App SDK)

1. Create Firebase project → **Authentication → Sign-in method** → enable **Google OAuth** (Email/password optional).
2. **Project settings → General → Your apps (Web)** → copy `apiKey`, `authDomain`, `projectId` → place in `.env.local`.
3. You don’t need Firebase Firestore (app SDK) for backend storage (we use **GCP Firestore Admin**), but the frontend may access Firestore for some features; our `firebase.ts` already forces long polling for stability.

### Google Cloud (Firestore + Storage + Signed URLs)

1. In **Google Cloud Console**: create a project.
2. Enable **Firestore (Native mode)** and **Cloud Storage**. Create a **bucket** (e.g., `makistry-dev-<yourname>`). Put its name in `GCS_BUCKET`.
3. **Service Account**:

   * Create a service account, download the JSON key, set `GOOGLE_APPLICATION_CREDENTIALS` to that path.
   * Grant roles: `Datastore User` (or `Cloud Datastore User`), `Storage Admin` (or `Storage Object Admin`).
   * For signed URLs, either:

     * Use the **same** service account in `GOOGLE_APPLICATION_CREDENTIALS` and set `SIGNING_SA_EMAIL` to that email **(recommended)**, **or**
     * Grant `roles/iam.serviceAccountTokenCreator` on `SIGNING_SA_EMAIL` to the default ADC principal so IAM Signer can mint V4 URLs.

> **Tip**: your bucket can be regional `us-central1`.

### AI Providers

#### **AWS Bedrock (Claude Sonnet)**

* In AWS Console → **Bedrock** → request access to Anthropic Claude Sonnet 4.
* Create an **IAM user** with programmatic access and permissions to use Bedrock invoke APIs.
* Put keys + region in `.env` (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`).
* No code changes needed; backend imports `app.agents.code_creation_aws.generate_cadquery` by default.

#### **Azure OpenAI**

* Create an Azure OpenAI resource, deploy all relevant models. Put endpoint/key and model names in `.env`.

---

## Local Setup & Running

### Backend (FastAPI)

1. **Create venv & install deps**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate      # Windows: .venv\Scripts\activate
   pip install --upgrade pip wheel
   pip install -r requirements.txt
   ```
2. **Verify CadQuery works**

   ```bash
   python -c "import cadquery as cq, OCP; print('CadQuery OK')"
   ```
3. **Start the backend API**

   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

   You should see `INFO: Uvicorn running on URL`.

### Frontend (Vite + React)

1. In the SPA folder (often repo root or `Makistry-frontend/`):

   ```bash
   npm ci
   npm run dev
   ```
2. Visit the localhost URL.

### Together (Frontend + Backend)

1. In the backend repo root:

   ```bash
   npm run dev
   ```
2. Visit the URL.

### Quick Smoke Test

1. **Sign up / Login** in the UI using Firebase (Email/Password). If you get stuck, see *Troubleshooting*.
2. Create a brainstorm in the landing page.
3. Click **Generate Design**. The backend will:

   * generate CAD code with your chosen AI provider
   * run CadQuery in a sandbox and upload STL → GCS
   * sign the STL path and expose via `/api/latest-cad`
4. The viewer should render the model once ready. Check the console for any 4xx/5xx.

---

## How Auth Works (End-to-End)

1. Frontend logs you into **Firebase Auth** (web SDK).
2. Frontend exchanges Firebase **ID token** for a **Makistry JWT** via `POST /api/auth/firebase` → backend verifies token using `firebase_admin` and issues a signed Makistry JWT.
3. Frontend stores Makistry JWT (see `src/lib/tokenManager.ts`) and attaches it to all `axios` calls (`Authorization: Bearer …`).
4. Backend protects routes using `get_current_user()`; if JWT expires, tokenManager refreshes via Firebase again.

> There’s also `POST /api/auth/firebase_custom` which returns a Firebase **custom token** if the backend needs to keep the client’s Firestore session alive.

## Branching, Commit Style, PRs

* **Branch** from `main` as `<your-name>`. DO NOT COMMIT TO MAIN.
* **Commits**: imperative, small, reference files or scope.
* **PRs**: include comprehensive documentation and descriptions for commits to your branch.

---

## Security & Secrets

* **Never** commit `.env` or service account JSONs.
* Use placeholders in docs/PRs.
* Assume everything you write in code reviews is public.

---

## Appendix — Handy cURL

```bash
# Health check
curl -s http://localhost:8000/api/healthz

# Latest CAD (needs Bearer token normally; for read-only you may still get 401)
curl -s "http://localhost:8000/api/latest-cad?project_id=proj_test"
```

