"""Supabase client factory.

Creates a Supabase Client from application settings.
The caller is responsible for caching the instance if needed.
"""

from bip.core.settings import Settings
from supabase import Client, create_client


def get_supabase_client(settings: Settings) -> Client:
    """Create and return a Supabase client from settings."""
    return create_client(settings.supabase_url, settings.supabase_key)
