import uuid
from flask import Blueprint, jsonify, request, current_app, send_from_directory
from werkzeug.utils import secure_filename
from .services.role_service import get_role_service
from .services.beat_service import get_beat_service
from .db.repository import save_job, get_job, list_jobs

api = Blueprint('api', __name__)

@api.route('/health', methods=['GET'])
def health_check():
    """Server health check endpoint."""
    return jsonify({
        "status": "ok",
        "service": "DrumGen-X Backend",
        "version": "0.1.0"
    })

@api.route('/output/<path:filename>')
def serve_output(filename):
    """Serve generated audio files."""
    return send_from_directory(current_app.config['OUTPUT_FOLDER'], filename)

@api.route('/v1/beat', methods=['POST'])
def generate_beat():
    """
    Generate a beat from an uploaded audio sample.
    Expected input:
    - bpm (float, default 120)
    - bars (int, default 4)
    - file (multipart/form-data)
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    try:
        bpm = float(request.form.get('bpm', 120))
        bars = int(request.form.get('bars', 4))
    except ValueError:
        return jsonify({"error": "Invalid bpm or bars value"}), 400

    # Save uploaded file
    filename = secure_filename(file.filename)
    job_id = str(uuid.uuid4())[:8]
    unique_filename = f"{job_id}_{filename}"
    upload_path = current_app.config['UPLOAD_FOLDER'] / unique_filename

    try:
        file.save(upload_path)
    except Exception as e:
        return jsonify({"error": f"Failed to save file: {e}"}), 500

    try:
        # Stage 2: Role Assignment
        role_service = get_role_service()
        pools = role_service.process_files([upload_path])

        # Stage 3: Beat Grid & Skeleton
        beat_service = get_beat_service()
        output_wav_name = f"render_{job_id}.wav"

        result = beat_service.generate_beat(
            pools,
            bpm=bpm,
            bars=bars,
            output_filename=output_wav_name
        )

        # Save to MongoDB
        request_data = {"bpm": bpm, "bars": bars, "filename": filename}
        save_job(job_id, request_data, result)

        return jsonify({
            "job_id": job_id,
            "message": "Beat generated successfully",
            "audio_url": result['audio_url'],
            "grid": result['grid'],
            "events_count": len(result['events'])
        })

    except Exception as e:
        current_app.logger.error(f"Processing error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

def _serialize_datetime(doc):
    """datetime 필드를 ISO 문자열로 변환 (이미 문자열이면 그대로)."""
    v = doc.get("created_at")
    if v and hasattr(v, "isoformat"):
        doc["created_at"] = v.isoformat()
    return doc

@api.route('/v1/beat/<job_id>', methods=['GET'])
def get_beat(job_id):
    """Retrieve a previously generated beat by job_id."""
    doc = get_job(job_id)
    if not doc:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(_serialize_datetime(doc))

@api.route('/v1/beats', methods=['GET'])
def list_beats():
    """List recent beat generation jobs."""
    limit = request.args.get('limit', 20, type=int)
    docs = list_jobs(limit=limit)
    return jsonify([_serialize_datetime(d) for d in docs])
