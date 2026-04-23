from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, Boolean, Index
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account = Column(String(50), nullable=False, index=True)
    status = Column(String(30), nullable=False, default="pending")
    # Status values: pending, scripting, generating_video, generating_tts,
    # subtitling, compositing, reviewing, uploading_drive, publishing,
    # published, failed, rejected

    title = Column(String(500))
    script_text = Column(Text)
    visual_prompts = Column(Text)       # JSON array
    hashtags = Column(Text)             # JSON array
    hook = Column(Text)

    narration_path = Column(String(500))
    video_clips = Column(Text)          # JSON array of paths
    subtitle_path = Column(String(500))
    final_path = Column(String(500))
    music_path = Column(String(500))

    quality_score = Column(Float)
    quality_notes = Column(Text)

    drive_file_id = Column(String(200))
    drive_url = Column(String(500))

    # Multi-platform publishing
    tiktok_url = Column(String(500))
    youtube_url = Column(String(500))
    tiktok_published = Column(Boolean, default=False)
    youtube_published = Column(Boolean, default=False)
    tiktok_enabled = Column(Boolean, default=True)   # per-video toggle
    youtube_enabled = Column(Boolean, default=True)   # per-video toggle

    retry_count = Column(Integer, default=0)
    error_message = Column(Text)
    estimated_duration = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)
    published_at = Column(DateTime)

    __table_args__ = (
        Index("idx_videos_account_status", "account", "status"),
        Index("idx_videos_status_created", "status", "created_at"),
        Index("idx_videos_created", "created_at"),
        Index("idx_videos_published_at", "published_at"),
    )

    def __repr__(self):
        return f"<Video {self.id} [{self.account}] {self.status}>"


class IdeaHistory(Base):
    __tablename__ = "idea_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account = Column(String(50), nullable=False, index=True)
    summary = Column(Text, nullable=False)
    title = Column(String(500))
    keywords = Column(String(200))  # compact tags for dedup: "haunted doll revenge"
    created_at = Column(DateTime, default=datetime.utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String(50), nullable=False)  # gemini, kling, elevenlabs
    label = Column(String(100))
    api_key = Column(String(500), nullable=False)
    enabled = Column(Boolean, default=True)

    usage_count = Column(Integer, default=0)
    usage_chars = Column(Integer, default=0)        # for ElevenLabs
    usage_reset_at = Column(DateTime)               # monthly reset

    failure_count = Column(Integer, default=0)
    cooldown_until = Column(DateTime)
    last_used_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_keys_provider", "provider", "enabled"),
    )

    def __repr__(self):
        return f"<ApiKey {self.id} [{self.provider}] {self.label}>"


class EmailThread(Base):
    __tablename__ = "email_threads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gmail_thread_id = Column(String(200), unique=True, nullable=False)
    gmail_message_id = Column(String(200))
    account = Column(String(50), index=True)  # which account's Gmail

    sender = Column(String(300))
    subject = Column(String(500))
    body_preview = Column(Text)

    category = Column(String(30))   # spam, sponsor, collab, legal, fan, otro
    confidence = Column(Float)

    auto_responded = Column(Boolean, default=False)
    response_text = Column(Text)
    needs_attention = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<EmailThread {self.id} [{self.account}:{self.category}] {self.subject}>"


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(Integer, nullable=False, index=True)
    step = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)     # success, failed, skipped

    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    duration_ms = Column(Integer)
    error_message = Column(Text)
    metadata_json = Column(Text)    # JSON: key used, retry count, etc.

    __table_args__ = (
        Index("idx_runs_video_step", "video_id", "step"),
        Index("idx_runs_status", "status"),
    )


class AuditLog(Base):
    """Append-only log of administrative actions (manual publish, toggles, etc.)."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor = Column(String(100))           # discord user id, "scheduler", "dashboard:<api-key-prefix>", "system"
    action = Column(String(80), nullable=False, index=True)
    target = Column(String(200))          # account, video id, platform, ...
    details = Column(Text)                # free-form, often JSON
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class VideoMetrics(Base):
    """Per-video, per-platform engagement snapshots (views/likes/shares).

    Filled in by an optional analytics job. Not used by core pipeline so it stays
    NULL-safe for users who never enable analytics.
    """
    __tablename__ = "video_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(Integer, nullable=False, index=True)
    platform = Column(String(20), nullable=False)        # tiktok | youtube
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    captured_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_metrics_video_platform", "video_id", "platform"),
    )

