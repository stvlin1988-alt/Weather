import os, sys, importlib, subprocess

# 確保 pkg_resources 存在（face_recognition_models 需要）
try:
    import pkg_resources
    print("=== pkg_resources: already available ===", flush=True)
except ImportError:
    print("=== pkg_resources: missing, installing setuptools... ===", flush=True)
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "setuptools"])
    importlib.invalidate_caches()
    import pkg_resources
    print("=== pkg_resources: installed OK ===", flush=True)

print("=== wsgi.py: starting create_app ===", flush=True)
try:
    from app import create_app
    app = create_app()
    print("=== wsgi.py: create_app OK ===", flush=True)
except Exception as e:
    print(f"=== wsgi.py: create_app FAILED: {e} ===", flush=True)
    sys.exit(1)
