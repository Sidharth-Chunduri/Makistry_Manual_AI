# app/services/gcp_clients.py
from functools import lru_cache
from google.cloud import storage as gcs
from google.cloud import firestore

@lru_cache(maxsize=1)
def get_storage_client() -> gcs.Client:
    return gcs.Client()

@lru_cache(maxsize=1)
def get_firestore_client() -> firestore.Client:
    return firestore.Client()
