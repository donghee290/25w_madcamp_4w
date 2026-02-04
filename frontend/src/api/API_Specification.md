### 공통 규칙

- Base URL: {VITE_API_BASE_URL}
- Content-Type:
    - JSON 요청/응답: application/json
    - 파일 업로드: multipart/form-data
- 응답 공통 필드
    - ok: boolean
    - error: string
- 상태 코드
    - 200 OK: 조회/성공
    - 201 Created: 생성 성공
    - 400 Bad Request: 요청값 검증 실패
    - 404 Not Found: project/job 없음
    - 409 Conflict: 중복 생성 등
    - 500 Internal Server Error: 서버 오류

### 데이터 모델

ProjectState

- created_at?: string (ISO 8601)
- uploads_dir?: string
- config: object
    - bpm: number
    - style: string
    - seed: number
    - progressive: boolean
    - repeat_full: number
    - export_format?: "wav" | "mp3" | "flac" | "ogg" | "m4a"
    - 기타 키 허용
- latest_s1_dir?: string
- latest_pools_json?: string
- latest_grid_json?: string
- latest_skeleton_json?: string
- latest_transformer_json?: string
- latest_event_grid_json?: string
- latest_editor_json?: string
- latest_audio_path?: string
- latest_export_format?: string
- latest_mp3?: string
- latest_wav?: string
- updated_at?: number

JobStatus

- job_id: string
- project_name: string
- status: "running" | "completed" | "failed"
- progress: string (예: "stage 2/8", "35%")
- result?: any (완료 시 산출물 요약/경로)
- error?: string (실패 시 메시지)
- created_at: number (unix epoch)

## API 명세서

### 1. 프로젝트 생성

**POST** `/api/projects`

Request (JSON)

- project_name?: string

```
{
	"project_name": "demo1"
}
```

Response 201 (JSON)

- ok: true
- project_name: string

```
{
	"ok": true,
	"project_name": "demo1"
}
```

동작 규칙

- project_name 미지정 시 서버가 자동 생성 (예: "proj_20260204_052800")
- 중복 이름이면 409 반환 또는 suffix 붙여 자동 생성(둘 중 하나로 고정)

Error 409

```
{
	"ok": false,
	"error": "project already exists"
}
```

### 2. 파일 업로드

**POST** `/api/projects/{projectName}/upload`

Path

- projectName: string

Request (multipart/form-data)

- audio: File (여러 개 허용)

Response 200

- ok: true
- project_name: string
- uploaded: array
    - name: string
    - size: number
    - saved_path: string

예시

```
{
	"ok": true,
	"project_name": "demo1",
	"uploaded": [
		{ "name": "a.wav", "size": 123456, "saved_path": "projects/demo1/uploads/a.wav" },
		{ "name": "b.wav", "size": 99999, "saved_path": "projects/demo1/uploads/b.wav" }
	]
}
```

Error 400 (파일 없음)

```
{
	"ok": false,
	"error": "no files in 'audio'"
}
```

### 3. 초기 생성(전체 파이프라인 실행)

**POST** `/api/projects/{projectName}/generate/initial` 

Path

- projectName: string

Request (JSON, optional)

- params: 자유 (beatApi에서 params를 통째로 body로 보냄)
    - 예: bpm, style, seed, export_format, progressive, repeat_full 등

예시

```
{
	"bpm": 120,
	"style": "house",
	"seed": 42,
	"export_format": "mp3",
	"progressive": true,
	"repeat_full": 1
}
```

Response 200

- ok: true
- job_id: string

예시

```
{
	"ok": true,
	"job_id": "job_20260204_052900_demo1"
}
```

동작 규칙

- 즉시 결과를 반환하지 말고 비동기 job으로 돌림
- job status는 /api/jobs/{jobId}로 폴링

Error 404

```
{
	"ok": false,
	"error": "project not found"
}
```

Error 400 (업로드 파일 없음 등)

```
{
	"ok": false,
	"error": "no uploaded audio found"
}
```

### 4. 프로젝트 상태 조회

**GET** `/api/projects/{projectName}/state` 

Path

- projectName: string

Response 200

- ok: true
- state: ProjectState

예시

```
{
	"ok": true,	
	"state": {	
		"created_at": "2026-02-04T05:28:00Z",		
		"uploads_dir": "projects/demo1/uploads",		
		"config": {		
			"bpm": 120,			
			"style": "house",			
			"seed": 42,			
			"progressive": true,			
			"repeat_full": 1,			
			"export_format": "mp3"		
		},		
		"latest_pools_json": "projects/demo1/out/pools.json",		
		"latest_editor_json": "projects/demo1/out/editor.json",		
		"latest_mp3": "projects/demo1/out/final.mp3",		
		"updated_at": 1738647000		
	}	
}
```

Error 404

```
{
	"ok": false,
	"error": "project not found"
}
```

### 5. 프로젝트 설정 업데이트

**PATCH** `/api/projects/{projectName}/config`

Path

- projectName: string

Request (JSON)

- config partial object (beatApi가 config 자체를 body로 보냄)

예시

```
{
	"bpm": 128,
	"export_format": "wav"
}
```

Response 200

- ok: true
- config: ProjectState.config (최신)

예시

```
{
	"ok": true,	
	"config": {
		"bpm": 128,		
		"style": "house",		
		"seed": 42,		
		"progressive": true,		
		"repeat_full": 1,		
		"export_format": "wav"		
	}
}
```

Error 400 (타입/범위 오류)

```
{
	"ok": false,
	"error": "bpm must be number"
}
```

### 6. 부분 재생성(특정 stage부터 다시)

**POST** `/api/projects/{projectName}/regenerate`

Path

- projectName: string

Request (JSON)

- from_stage: number (필수)
- params?: any (선택)

예시

```
{
	"from_stage": 4,
	"params": {
		"seed": 99,
		"repeat_full": 2
	}
}
```

Response 200

- ok: true
- job_id: string

예시

```
{
	"ok": true,
	"job_id": "job_20260204_053100_demo1_s4"
}
```

동작 규칙

- from_stage 기준으로 파이프라인 일부만 재실행
- 역시 job 비동기 처리 권장

Error 400

```
{
	"ok": false,
	"error": "from_stage is required and must be a number"
}
```

### 7. 잡 상태 폴링

**GET** `/api/jobs/{jobId}`

Path

- jobId: string

Response 200

- ok: true
- job: JobStatus

예시(running)

```
{
	"ok": true,
	"job": {
		"job_id": "job_20260204_053100_demo1_s4",
		"project_name": "demo1",
		"status": "running",
		"progress": "stage 5/8",
		"created_at": 1738647060
	}
}
```

예시(completed)

```
{
	"ok": true,
	"job": {
		"job_id": "job_20260204_053100_demo1_s4",
		"project_name": "demo1",
		"status": "completed",
		"progress": "done",
		"result": {
			"latest_mp3": "projects/demo1/out/final.mp3",
			"latest_editor_json": "projects/demo1/out/editor.json"
		},
		"created_at": 1738647060
	}
}
```

예시(failed)

```
{
	"ok": true,
	"job": {
		"job_id": "job_20260204_053100_demo1_s4",
		"project_name": "demo1",
		"status": "failed",
		"progress": "error",
		"error": "CUDA out of memory",
		"created_at": 1738647060
	}
}
```

Error 404

```
{
	"ok": false,
	"error": "job not found"
}
```

### 8. 결과 다운로드

**GET** `/api/projects/{projectName}/download?kind=mp3` 

Path

- projectName: string

Query

- kind: string (default: mp3)
    - 허용: wav, mp3, flac, ogg, m4a (권장)

Response 200

- 파일 스트림 (Content-Disposition attachment 권장)
- Content-Type은 파일 종류에 맞게

Error 404

```
{
	"ok": false,
	"error": "file not found"
}
```