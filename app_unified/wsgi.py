import os, sys
print(f"=== wsgi.py: PORT={os.environ.get('PORT', 'NOT SET')} ===", flush=True)
print("=== wsgi.py: starting create_app ===", flush=True)
try:
    from app import create_app
    app = create_app()
    print("=== wsgi.py: create_app OK ===", flush=True)
except Exception as e:
    print(f"=== wsgi.py: create_app FAILED: {e} ===", flush=True)
    sys.exit(1)
