import os

# Ensure dummy env vars are present before config.py is imported.
os.environ.setdefault("GROQ_API_KEY", "gsk_dummy_key_for_testing_only")
os.environ.setdefault("PROVIDER", "groq")
os.environ.setdefault("MODEL", "groq/llama-3.3-70b-versatile")
