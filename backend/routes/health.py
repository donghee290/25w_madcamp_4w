from flask import Blueprint, jsonify, current_app

health_bp = Blueprint("health", __name__)

@health_bp.get("/api/health")
def health():
    """
    Server status check.
    """
    # Check if services are attached to app
    has_services = (
        hasattr(current_app, "state_manager") and 
        hasattr(current_app, "pipeline_service")
    )
    return jsonify({
        "ok": True, 
        "model_connected": has_services
    })
