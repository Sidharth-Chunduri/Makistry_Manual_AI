import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AliasChoices

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=False)     # loads AZURE_* vars

# Manually set environment variables that need to be available to pydantic-settings
env_vars_from_dotenv = {}
with open(ROOT / ".env", "r") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env_vars_from_dotenv[key.strip()] = value.strip()
            # Set in actual environment for pydantic-settings
            os.environ.setdefault(key.strip(), value.strip())

class Settings(BaseSettings):
    # shared endpoint & key
    endpoint: str = Field(validation_alias="AZURE_OAI_ENDPOINT")
    api_key:  str = Field(validation_alias="AZURE_OAI_KEY")

    # brainstorm (gpt-4.1) deployment
    bstorm_model: str = Field(validation_alias="AZURE_BSTORM_MODEL")
    bstorm_api_ver: str = Field(validation_alias="AZURE_BSTORM_API_VERSION")

    #brainstorm-edit (gpt-4.1-mini) deployment
    bstorm_edit_model: str = Field(validation_alias="AZURE_BSTORM_EDIT_MODEL")
    bstorm_edit_api_ver: str = Field(validation_alias="AZURE_BSTORM_EDIT_API_VERSION")

    sim_model: str = Field(validation_alias="AZURE_SIM_MODEL")
    sim_api_ver: str = Field(validation_alias="AZURE_SIM_API_VERSION")
    # simulation-edit (gpt-4.1-mini) deployment
    sim_edit_model: str = Field(validation_alias="AZURE_SIM_EDIT_MODEL")
    sim_edit_api_ver: str = Field(validation_alias="AZURE_SIM_EDIT_API_VERSION")

    # code-creation (o4-mini) deployment
    code_model: str = Field(validation_alias="AZURE_CODE_MODEL")
    code_api_ver: str = Field(validation_alias="AZURE_CODE_API_VERSION")

    code_edit_model: str = Field(validation_alias="AZURE_CODE_EDIT_MODEL")
    code_edit_api_ver: str = Field(validation_alias="AZURE_CODE_EDIT_API_VERSION")

    # intent-classification (gpt-4.1-mini) deployment
    intent_model: str = Field(validation_alias="AZURE_INTENT_MODEL")
    intent_api_ver: str = Field(validation_alias="AZURE_INTENT_API_VERSION")

    # chat agent (gpt-4.1) deployment
    chat_model: str = Field(validation_alias="AZURE_CHAT_MODEL")
    chat_api_ver: str = Field(validation_alias="AZURE_CHAT_API_VERSION")

    # planner agent (o4-mini)
    plan_model: str = Field(validation_alias="AZURE_CODE_MODEL")
    plan_api_ver: str = Field(validation_alias="AZURE_CODE_API_VERSION")

    # ───────────────── Cosmos DB ────────────────────
    cosmos_endpoint: str     = Field(..., env="COSMOS_ENDPOINT")
    cosmos_key: str          = Field(..., env="COSMOS_KEY")
    cosmos_db: str           = Field("makistry", env="COSMOS_DB")

    # ───────────────── Blob Storage ────────────────
    blob_account: str        = Field(..., validation_alias="AZURE_BLOB_ACCOUNT_NAME")
    blob_key: str            = Field(..., validation_alias="AZURE_BLOB_ACCOUNT_KEY")
    blob_container: str      = Field(..., validation_alias="AZURE_BLOB_CONTAINER")

    # ───────────────── JWT secret (simple) ─────────
    jwt_secret: str          = Field("dev-secret", env="JWT_SECRET")
    jwt_alg: str = "HS256"
    access_ttl_h: int = 24

    # ───────────────── GCP / Firestore / Cloud Storage ───────────────
    storage_backend: str = Field("gcp", validation_alias="STORAGE_BACKEND")

    # Map multiple possible env names to each field for robustness
    gcp_project: str = Field(
        ...,
        validation_alias=AliasChoices(
            "GCP_PROJECT_ID",      # you set this
            "GCLOUD_PROJECT",      # gcloud default
            "GOOGLE_CLOUD_PROJECT" # older samples
        ),
    )
    gcs_bucket: str = Field(
        ...,
        validation_alias=AliasChoices("GCS_BUCKET", "GOOGLE_CLOUD_STORAGE_BUCKET")
    )
    gcp_credentials_path: str | None = Field(
        None,
        validation_alias=AliasChoices("GOOGLE_APPLICATION_CREDENTIALS", "GCP_CREDENTIALS")
    )
    
    # GCS Signing Service Account Email
    signing_sa_email: str = Field(..., env="SIGNING_SA_EMAIL")
    
    # Firebase keys (for web and backend)  
    firebase_api_key: str = Field(..., env="FIREBASE_API_KEY")
    vite_firebase_api_key: str = Field(..., env="VITE_FIREBASE_API_KEY")
    vite_firebase_auth_domain: str = Field(..., env="VITE_FIREBASE_AUTH_DOMAIN")
    vite_firebase_project_id: str = Field(..., env="VITE_FIREBASE_PROJECT_ID")

    # AWS BEDROCK
    aws_region: str = Field("us-east-1", validation_alias="AWS_REGION")
    aws_access_key_id: str | None = Field(None, validation_alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str | None = Field(None, validation_alias="AWS_SECRET_ACCESS_KEY")
    aws_bearer_token_bedrock: str | None = Field(None, env="AWS_BEARER_TOKEN_BEDROCK")
    sonnet_model_id: str = Field(
        "us.anthropic.claude-sonnet-4-20250514-v1:0",
        validation_alias="SONNET_MODEL_ID",
    )

    ui_origin: str = Field(
        "http://localhost:8080",
        validation_alias=AliasChoices("UI_ORIGIN")
    )

    # (optional) choose backend at runtime: "gcp" or "azure"

    model_config = SettingsConfigDict(case_sensitive=False, env_file='.env', extra='allow')

    # Resend
    resend_api_key: str = Field(..., env="RESEND_API_KEY")
    resend_domain: str = Field(
        "makistry.com",  # default domain, can be overridden
        env="RESEND_DOMAIN"
    )

    # Stripe
    stripe_secret_key: str = Field(..., env="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str = Field(..., env="STRIPE_WEBHOOK_SECRET")
    stripe_price_plus_monthly: str = Field(..., env="STRIPE_PRICE_PLUS_MONTHLY")
    stripe_price_pro_monthly: str = Field(..., env="STRIPE_PRICE_PRO_MONTHLY")

settings = Settings()

import os as _os, sys as _sys
if settings.gcp_credentials_path:
    _os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", settings.gcp_credentials_path)
else:
    print("[Makistry] WARNING: GOOGLE_APPLICATION_CREDENTIALS not set; relying on ADC.", file=_sys.stderr)

# Hard-fail if someone sets a different backend
if settings.storage_backend.lower() != "gcp":
    raise RuntimeError("Makistry is GCP-only now. Set STORAGE_BACKEND=gcp.")