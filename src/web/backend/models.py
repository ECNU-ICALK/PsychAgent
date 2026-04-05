from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field as SQLField, SQLModel


class TherapyCourseRecord(SQLModel, table=True):
    __tablename__ = "therapycourse"

    course_id: str = SQLField(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    user_id: str = SQLField(index=True, nullable=False)
    school_id: str = SQLField(index=True, nullable=False)
    title: str = SQLField(default="", nullable=False)
    status: str = SQLField(default="active", index=True, nullable=False)
    current_stage_key: str = SQLField(default="assessment", nullable=False)
    planned_visit_count: Optional[int] = SQLField(default=None, nullable=True)
    latest_visit_no: int = SQLField(default=0, nullable=False)
    active_visit_id: Optional[str] = SQLField(default=None, index=True, nullable=True)
    goal_summary: str = SQLField(default="", nullable=False)
    intake_note: str = SQLField(default="", nullable=False)
    summary: str = SQLField(default="", nullable=False)
    last_message_at: datetime = SQLField(default_factory=datetime.utcnow, nullable=False)
    created_at: datetime = SQLField(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = SQLField(default_factory=datetime.utcnow, nullable=False)


class TherapyVisitRecord(SQLModel, table=True):
    __tablename__ = "therapyvisit"
    __table_args__ = (UniqueConstraint("course_id", "visit_no", name="uq_therapyvisit_course_visit_no"),)

    visit_id: str = SQLField(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    course_id: str = SQLField(index=True, nullable=False)
    visit_no: int = SQLField(nullable=False)
    stage_key_snapshot: str = SQLField(nullable=False)
    status: str = SQLField(default="open", index=True, nullable=False)
    started_at: datetime = SQLField(default_factory=datetime.utcnow, nullable=False)
    ended_at: Optional[datetime] = SQLField(default=None, nullable=True)
    summary: str = SQLField(default="", nullable=False)
    message_count: int = SQLField(default=0, nullable=False)
    created_at: datetime = SQLField(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = SQLField(default_factory=datetime.utcnow, nullable=False)
    legacy_session_id: Optional[str] = SQLField(default=None, nullable=True)


class VisitMessageRecord(SQLModel, table=True):
    __tablename__ = "visitmessage"

    id: str = SQLField(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    visit_id: str = SQLField(index=True, nullable=False)
    role: str = SQLField(nullable=False)
    text: str = SQLField(nullable=False)
    created_at: datetime = SQLField(default_factory=datetime.utcnow, nullable=False)


class VisitPsychContextRecord(SQLModel, table=True):
    __tablename__ = "visitpsychcontext"

    visit_id: str = SQLField(primary_key=True, index=True)
    client_info_json: str = SQLField(default="{}", nullable=False)
    session_focus_json: str = SQLField(default="[]", nullable=False)
    history_json: str = SQLField(default="[]", nullable=False)
    homework_json: str = SQLField(default="[]", nullable=False)
    summary_payload_json: str = SQLField(default="{}", nullable=False)
    profile_payload_json: str = SQLField(default="{}", nullable=False)
    source: str = SQLField(default="derived_from_course_data_v1", nullable=False)
    created_at: datetime = SQLField(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = SQLField(default_factory=datetime.utcnow, nullable=False)


class CourseGoalRecord(SQLModel, table=True):
    __tablename__ = "coursegoal"

    goal_id: str = SQLField(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    course_id: str = SQLField(index=True, nullable=False)
    content: str = SQLField(nullable=False)
    sort_order: int = SQLField(default=0, nullable=False)
    status: str = SQLField(default="active", nullable=False)
    created_at: datetime = SQLField(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = SQLField(default_factory=datetime.utcnow, nullable=False)


class MigrationStateRecord(SQLModel, table=True):
    __tablename__ = "migrationstate"

    migration_key: str = SQLField(primary_key=True, index=True)
    status: str = SQLField(default="completed", nullable=False)
    details_json: str = SQLField(default="{}", nullable=False)
    applied_at: datetime = SQLField(default_factory=datetime.utcnow, nullable=False)


class UserRecord(SQLModel, table=True):
    __tablename__ = "userrecord"

    id: str = SQLField(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    username: str = SQLField(unique=True, index=True, nullable=False)
    password_hash: str = SQLField(nullable=False)
    created_at: datetime = SQLField(default_factory=datetime.utcnow, nullable=False)


class AuthTokenRecord(SQLModel, table=True):
    __tablename__ = "authtokenrecord"

    token: str = SQLField(primary_key=True, index=True)
    user_id: str = SQLField(index=True, nullable=False)
    created_at: datetime = SQLField(default_factory=datetime.utcnow, nullable=False)


class UserGlobalProfileRecord(SQLModel, table=True):
    __tablename__ = "userglobalprofile"

    user_id: str = SQLField(primary_key=True, index=True)
    base_profile_json: str = SQLField(default="{}", nullable=False)
    source: str = SQLField(default="profile_sync_v1", nullable=False)
    created_at: datetime = SQLField(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = SQLField(default_factory=datetime.utcnow, nullable=False)
