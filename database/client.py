import os
from typing import Optional
from supabase import Client, create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "") or os.environ.get(
    "SUPABASE_SERVICE_ROLE_KEY", ""
)


def _validate_supabase_url(url: str) -> bool:
    return url.startswith("https://") and ".supabase.co" in url


def _validate_key(key: str) -> bool:
    return bool(key and len(key) > 50)


def get_supabase_client() -> Client:
    if not _validate_supabase_url(SUPABASE_URL) or not _validate_key(SUPABASE_ANON_KEY):
        raise EnvironmentError(
            "SUPABASE_URL and SUPABASE_ANON_KEY must be set and valid in the environment"
        )
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def get_supabase_service_client() -> Client:
    if not _validate_supabase_url(SUPABASE_URL) or not _validate_key(SUPABASE_SERVICE_KEY):
        raise EnvironmentError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY (or SUPABASE_SERVICE_ROLE_KEY) must be set and valid in the environment"
        )
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def health_check(use_service_client: bool = False, check_table: str = "system_settings") -> bool:
    try:
        client = get_supabase_service_client() if use_service_client else get_supabase_client()
        response = client.table(check_table).select("*").limit(1).execute()
        return response is not None and hasattr(response, "data")
    except Exception:
        return False
