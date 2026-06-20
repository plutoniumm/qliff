from .app import create_app

# The Studio web server backs the `qliff` command and needs the [studio] extra
# (fastapi, uvicorn, pymatching, ldpc). Never imported by `import qliff`, so the
# core stays numpy-only.

__all__ = ["create_app"]
