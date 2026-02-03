"""
SoundRoutine Database Models
MongoDB 스키마 기반 데이터 모델
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid


def utc_now() -> str:
    """현재 UTC 시간 ISO 형식"""
    return datetime.now(timezone.utc).isoformat()


def generate_id() -> str:
    """고유 ID 생성"""
    return uuid.uuid4().hex


# ============================================================================
# Users Collection
# ============================================================================
@dataclass
class User:
    """사용자 모델"""
    user_id: str
    google_id: str  # 구글 OAuth sub 값 (Unique Index)
    email: str
    name: str
    picture: Optional[str] = None
    last_login: str = field(default_factory=utc_now)
    created_at: str = field(default_factory=utc_now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "google_id": self.google_id,
            "email": self.email,
            "name": self.name,
            "picture": self.picture,
            "last_login": self.last_login,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> User:
        return cls(
            user_id=data.get("user_id", generate_id()),
            google_id=data["google_id"],
            email=data["email"],
            name=data["name"],
            picture=data.get("picture"),
            last_login=data.get("last_login", utc_now()),
            created_at=data.get("created_at", utc_now()),
        )
    
    @classmethod
    def from_google_userinfo(cls, userinfo: Dict[str, Any]) -> User:
        """Google OAuth userinfo로부터 생성"""
        return cls(
            user_id=generate_id(),
            google_id=userinfo["sub"],
            email=userinfo["email"],
            name=userinfo.get("name", ""),
            picture=userinfo.get("picture"),
        )


# ============================================================================
# Tokens Collection (JWT 토큰 저장)
# ============================================================================
@dataclass
class RefreshToken:
    """Refresh Token 모델 - DB에 저장되어 토큰 관리에 사용"""
    token_id: str
    user_id: str
    token_hash: str  # 토큰 해시값 (보안을 위해 원본 저장 안함)
    device_info: str = ""  # 접속 기기 정보
    ip_address: str = ""  # 접속 IP
    is_revoked: bool = False  # 무효화 여부
    expires_at: str = field(default_factory=utc_now)
    created_at: str = field(default_factory=utc_now)
    last_used_at: str = field(default_factory=utc_now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "token_id": self.token_id,
            "user_id": self.user_id,
            "token_hash": self.token_hash,
            "device_info": self.device_info,
            "ip_address": self.ip_address,
            "is_revoked": self.is_revoked,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RefreshToken:
        return cls(
            token_id=data.get("token_id", generate_id()),
            user_id=data["user_id"],
            token_hash=data["token_hash"],
            device_info=data.get("device_info", ""),
            ip_address=data.get("ip_address", ""),
            is_revoked=data.get("is_revoked", False),
            expires_at=data.get("expires_at", utc_now()),
            created_at=data.get("created_at", utc_now()),
            last_used_at=data.get("last_used_at", utc_now()),
        )


@dataclass
class ActiveSession:
    """활성 세션 모델 - 사용자의 로그인 세션 추적"""
    session_id: str
    user_id: str
    access_token_jti: str  # Access Token의 JTI (JWT ID)
    refresh_token_id: str  # 연결된 RefreshToken ID
    device_info: str = ""
    ip_address: str = ""
    is_active: bool = True
    created_at: str = field(default_factory=utc_now)
    last_activity: str = field(default_factory=utc_now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "access_token_jti": self.access_token_jti,
            "refresh_token_id": self.refresh_token_id,
            "device_info": self.device_info,
            "ip_address": self.ip_address,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ActiveSession:
        return cls(
            session_id=data.get("session_id", generate_id()),
            user_id=data["user_id"],
            access_token_jti=data["access_token_jti"],
            refresh_token_id=data["refresh_token_id"],
            device_info=data.get("device_info", ""),
            ip_address=data.get("ip_address", ""),
            is_active=data.get("is_active", True),
            created_at=data.get("created_at", utc_now()),
            last_activity=data.get("last_activity", utc_now()),
        )



# ============================================================================
# Sounds Collection
# ============================================================================
@dataclass
class DSPAnalysis:
    """DSP 분석 결과"""
    energy: float = 0.0
    sharpness: float = 0.0
    attack: float = 0.0
    decay: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "energy": self.energy,
            "sharpness": self.sharpness,
            "attack": self.attack,
            "decay": self.decay,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DSPAnalysis:
        return cls(
            energy=data.get("energy", 0.0),
            sharpness=data.get("sharpness", 0.0),
            attack=data.get("attack", 0.0),
            decay=data.get("decay", 0.0),
        )


@dataclass
class SoundAnalysis:
    """AI 분석 결과"""
    role: str = "CORE"  # CORE, ACCENT, MOTION, FILL, TEXTURE
    dsp: DSPAnalysis = field(default_factory=DSPAnalysis)
    embedding: List[float] = field(default_factory=list)  # 1024-d 벡터
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "dsp": self.dsp.to_dict(),
            "embedding": self.embedding[:100] if self.embedding else [],  # 저장 시 축소
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SoundAnalysis:
        return cls(
            role=data.get("role", "CORE"),
            dsp=DSPAnalysis.from_dict(data.get("dsp", {})),
            embedding=data.get("embedding", []),
        )


@dataclass
class Sound:
    """사운드 샘플 모델"""
    sound_id: str
    user_id: str
    file_path: str  # 로컬 파일 경로
    file_name: str  # 원본 파일명
    status: str = "pending"  # pending, validated, deleted
    slot_index: int = 0  # 0-9
    analysis: SoundAnalysis = field(default_factory=SoundAnalysis)
    duration: float = 0.0  # 초 단위
    created_at: str = field(default_factory=utc_now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sound_id": self.sound_id,
            "user_id": self.user_id,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "status": self.status,
            "slot_index": self.slot_index,
            "analysis": self.analysis.to_dict(),
            "duration": self.duration,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Sound:
        return cls(
            sound_id=data.get("sound_id", generate_id()),
            user_id=data["user_id"],
            file_path=data["file_path"],
            file_name=data.get("file_name", ""),
            status=data.get("status", "pending"),
            slot_index=data.get("slot_index", 0),
            analysis=SoundAnalysis.from_dict(data.get("analysis", {})),
            duration=data.get("duration", 0.0),
            created_at=data.get("created_at", utc_now()),
        )


# ============================================================================
# Projects Collection
# ============================================================================
@dataclass
class NoteEvent:
    """시퀀서 노트 이벤트"""
    bar: int
    step: int
    sound_id: str
    role: str  # CORE, ACCENT, MOTION, FILL, TEXTURE
    velocity: float = 1.0
    micro_offset: float = 0.0  # GrooVAE 미세 타이밍
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "bar": self.bar,
            "step": self.step,
            "sound_id": self.sound_id,
            "role": self.role,
            "velocity": self.velocity,
            "micro_offset": self.micro_offset,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> NoteEvent:
        return cls(
            bar=data["bar"],
            step=data["step"],
            sound_id=data["sound_id"],
            role=data.get("role", "CORE"),
            velocity=data.get("velocity", 1.0),
            micro_offset=data.get("micro_offset", 0.0),
        )


@dataclass
class ProjectMetadata:
    """프로젝트 메타데이터"""
    beat_name: str = "Untitled Beat"
    group_name: str = "Default Group"
    bpm: int = 120
    grid_res: int = 16  # 8, 16, 32, 64
    time_signature: str = "4/4"
    is_progressive: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "beat_name": self.beat_name,
            "group_name": self.group_name,
            "bpm": self.bpm,
            "grid_res": self.grid_res,
            "time_signature": self.time_signature,
            "is_progressive": self.is_progressive,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ProjectMetadata:
        return cls(
            beat_name=data.get("beat_name", "Untitled Beat"),
            group_name=data.get("group_name", "Default Group"),
            bpm=data.get("bpm", 120),
            grid_res=data.get("grid_res", 16),
            time_signature=data.get("time_signature", "4/4"),
            is_progressive=data.get("is_progressive", False),
        )


@dataclass
class Sequence:
    """시퀀스 데이터"""
    total_pages: int = 1  # Max 128
    current_page: int = 1
    events: List[NoteEvent] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_pages": self.total_pages,
            "current_page": self.current_page,
            "events": [e.to_dict() for e in self.events],
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Sequence:
        return cls(
            total_pages=data.get("total_pages", 1),
            current_page=data.get("current_page", 1),
            events=[NoteEvent.from_dict(e) for e in data.get("events", [])],
        )


@dataclass
class Project:
    """비트 프로젝트 모델"""
    project_id: str
    user_id: str
    metadata: ProjectMetadata = field(default_factory=ProjectMetadata)
    sequence: Sequence = field(default_factory=Sequence)
    sound_slots: Dict[str, str] = field(default_factory=dict)  # role -> sound_id
    output_path: Optional[str] = None  # 렌더링된 오디오 파일 경로
    status: str = "draft"  # draft, generating, completed
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "user_id": self.user_id,
            "metadata": self.metadata.to_dict(),
            "sequence": self.sequence.to_dict(),
            "sound_slots": self.sound_slots,
            "output_path": self.output_path,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Project:
        return cls(
            project_id=data.get("project_id", generate_id()),
            user_id=data["user_id"],
            metadata=ProjectMetadata.from_dict(data.get("metadata", {})),
            sequence=Sequence.from_dict(data.get("sequence", {})),
            sound_slots=data.get("sound_slots", {}),
            output_path=data.get("output_path"),
            status=data.get("status", "draft"),
            created_at=data.get("created_at", utc_now()),
            updated_at=data.get("updated_at", utc_now()),
        )


# ============================================================================
# Legacy Compatibility
# ============================================================================
@dataclass
class JobRecord:
    """기존 Job Record (호환성 유지)"""
    job_id: str
    status: str
    created_at: str
    input_meta: Dict[str, Any]
    output_meta: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
