def create_app():
    # Lazy import to avoid heavy deps (torch/flask) on module import
    from .api import create_app as _create_app

    return _create_app()


__all__ = ["create_app"]
