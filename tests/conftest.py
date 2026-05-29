"""Test configuration.

Injects placeholder env vars BEFORE app.config is imported so unit tests
never touch live services. Integration tests opt into real credentials with
the `integration` marker — they're skipped by default.
"""
import os

# Required by app.config.Settings — must be set before any app.* import.
_DEFAULTS = {
    "ANTHROPIC_API_KEY": "test-anthropic-key",
    "OPENAI_API_KEY": "test-openai-key",
    "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_ANON_KEY": "test-anon-key",
    "UPSTASH_REDIS_REST_URL": "https://test.upstash.io",
    "UPSTASH_REDIS_REST_TOKEN": "test-redis-token",
    "LANGSMITH_API_KEY": "test-langsmith-key",
    "LANGSMITH_PROJECT": "harness-rag-test",
    "LANGSMITH_TRACING": "false",
    "ADMIN_KEY": "test-admin-key",
}

for k, v in _DEFAULTS.items():
    os.environ.setdefault(k, v)
