from gevent import monkey
monkey.patch_all()

import os, sys, types

# pkg_resources 替代方案：用 importlib 提供 resource_filename
try:
    import pkg_resources
    print("=== pkg_resources: available ===", flush=True)
except ImportError:
    print("=== pkg_resources: missing, creating shim ===", flush=True)
    pkg_resources = types.ModuleType("pkg_resources")

    def _resource_filename(package_or_req, resource_name):
        import importlib
        mod = importlib.import_module(str(package_or_req))
        mod_dir = os.path.dirname(mod.__file__)
        return os.path.join(mod_dir, resource_name)

    pkg_resources.resource_filename = _resource_filename
    sys.modules["pkg_resources"] = pkg_resources
    print("=== pkg_resources shim: OK ===", flush=True)

print("=== wsgi.py: starting create_app ===", flush=True)
try:
    from app import create_app
    app = create_app()
    from extensions import socketio
    print("=== wsgi.py: create_app OK ===", flush=True)
except Exception as e:
    print(f"=== wsgi.py: create_app FAILED: {e} ===", flush=True)
    sys.exit(1)
