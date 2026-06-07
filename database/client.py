import os
from supabase import Client, create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def get_supabase_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise EnvironmentError(
            "SUPABASE_URL and SUPABASE_ANON_KEY must be set in environment"
        )
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def get_supabase_service_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise EnvironmentError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in environment"
        )
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
