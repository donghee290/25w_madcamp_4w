# SoundRoutine Server README

**SoundRoutine** is a full‑stack drum beat generator with a React frontend, an Express (Node) API, and a Flask model server running a 7‑stage ML pipeline.

**Services And Ports**
- Frontend (Vite + React): `http://localhost:3000` (or `3001` if 3000 is busy)
- Node API (Express): `http://localhost:5000`
- Model API (Flask): `http://localhost:8001`

The frontend talks to **Node (5000)**, and Node **proxies `/api/*` to the model server (8001)**.

---

**Quick Start (Windows PowerShell)**

1. Create and activate venv
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install Python deps
```powershell
pip install -r backend/requirements.txt
pip install -r model/requirements.txt
pip install demucs
```

3. Install Node deps
```powershell
cd backend
npm install
cd ..\frontend
npm install
```

4. Set environment variables
- `frontend/.env`
```text
VITE_API_BASE_URL=http://localhost:5000
```
- `backend/.env` (example)
```text
MONGO_URI=mongodb://127.0.0.1:27017/soundroutine
JWT_SECRET=change_me
MODEL_BASE_URL=http://127.0.0.1:8001
```
- Optional HF cache (prevents invalid drive issues)
```powershell
$env:HF_HOME="C:\Project\kaist\4_week\25w_madcamp_4w\.cache\hf"
$env:TRANSFORMERS_CACHE="$env:HF_HOME\transformers"
```

---

**Run Servers**

1. Model server (Flask)
```powershell
$env:PORT=8001
python -m backend.app
```

2. Node API (Express)
```powershell
node backend\server.js
```

3. Frontend (Vite)
```powershell
cd frontend
npm run dev
```
If port 3000 is busy:
```powershell
npm run dev -- --port 3000
```

---

**Health Checks**
```powershell
curl http://localhost:8001/api/health
curl -X POST http://localhost:5000/api/beats -H "Content-Type: application/json" -d "{}"
```

---

**Outputs**
- Generated data lives under `outs/beat_<timestamp>/`
- Final audio is served at:
```text
http://localhost:5000/api/beats/<beat_name>/download?kind=wav
```

---

**Common Issues**

1. **Frontend shows “connection refused”**
- Vite likely moved to `3001`. Open `http://localhost:3001`.

2. **Stage 2 fails with cache path errors**
- Ensure `HF_HOME` and `TRANSFORMERS_CACHE` have no trailing spaces.
- Point them to `.cache\hf` as shown above.

3. **No sound in output**
- The file may be generated but too quiet.
- Re‑render stage 7:
```powershell
Invoke-RestMethod -Method Post http://localhost:5000/api/beats/<beat_name>/regenerate -Body '{"from_stage":7}' -ContentType 'application/json'
```

4. **HF symlink warning on Windows**
- Safe to ignore. To remove it, enable Developer Mode or run as Administrator.

---

**Notes**
- `backend/app.py` is the **model server** used by the pipeline.
- Node handles auth (`/auth/register`, `/auth/login`) and proxies `/api/*` to the model server.
