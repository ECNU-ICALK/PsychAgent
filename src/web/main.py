from __future__ import annotations

import hashlib
import logging
import os
import secrets
import sys
from datetime import datetime
from pathlib import Path
from typing import List

APP_DIR = Path(__file__).resolve().parent
SRC_DIR = APP_DIR.parent
PROJECT_ROOT = APP_DIR.parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import Session, SQLModel, create_engine, select

from backend.domain import SCHOOLS, STAGES, SchoolInfo, StageInfo, stage_from_key
from backend.models import AuthTokenRecord, UserRecord
from backend.psychagent_engine import PsychAgentWebBackend
from backend.routes.courses import create_courses_router
from backend.routes.visits import create_visits_router

LOGGER = logging.getLogger("psychagent_web")
BASELINE_CONFIG_PATH = Path(
    os.environ.get(
        "PSYCHAGENT_WEB_BASELINE_CONFIG",
        "configs/baselines/psychagent_sglang_local.yaml",
    )
)
RUNTIME_CONFIG_PATH = Path(
    os.environ.get(
        "PSYCHAGENT_WEB_RUNTIME_CONFIG",
        "configs/runtime/psychagent_sglang_local.yaml",
    )
)
DB_URL = os.environ.get("DB_URL", f"sqlite:///{(APP_DIR / 'data.db').resolve()}")
CONNECT_ARGS = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
engine = create_engine(DB_URL, echo=False, connect_args=CONNECT_ARGS)
_psychagent_backend: PsychAgentWebBackend | None = None


class UserOut(BaseModel):
    id: str
    username: str
    created_at: datetime


class AuthResponse(BaseModel):
    token: str
    user: UserOut


class AuthPayload(BaseModel):
    username: str
    password: str


app = FastAPI(title="PsychAgent Web API", version="0.4.2")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def configure_logging() -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def get_psychagent_backend() -> PsychAgentWebBackend:
    global _psychagent_backend
    if _psychagent_backend is None:
        _psychagent_backend = PsychAgentWebBackend(
            project_root=PROJECT_ROOT,
            baseline_config_path=BASELINE_CONFIG_PATH,
            runtime_config_path=RUNTIME_CONFIG_PATH,
            logger=LOGGER,
        )
    return _psychagent_backend


def run_sqlite_migrations() -> None:
    if not DB_URL.startswith("sqlite"):
        return

    def ensure_column(table: str, column: str, definition_sql: str) -> None:
        rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
        exists = any(len(row) > 1 and row[1] == column for row in rows)
        if exists:
            return
        conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {definition_sql}")

    with engine.connect() as conn:
        try:
            conn.exec_driver_sql("DROP INDEX IF EXISTS ux_therapycourse_user_school_active")
        except Exception as exc:
            LOGGER.warning("failed to drop ux_therapycourse_user_school_active: %s", exc)
        try:
            conn.exec_driver_sql("DROP INDEX IF EXISTS ux_therapycourse_user_active")
        except Exception as exc:
            LOGGER.warning("failed to drop ux_therapycourse_user_active: %s", exc)
        try:
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_therapyvisit_course_open "
                "ON therapyvisit(course_id) WHERE status = 'open'"
            )
        except Exception as exc:
            LOGGER.warning("failed to create ux_therapyvisit_course_open: %s", exc)
        try:
            ensure_column(
                table="visitpsychcontext",
                column="summary_payload_json",
                definition_sql="summary_payload_json TEXT NOT NULL DEFAULT '{}'",
            )
        except Exception as exc:
            LOGGER.warning("failed to add visitpsychcontext.summary_payload_json: %s", exc)
        try:
            ensure_column(
                table="visitpsychcontext",
                column="profile_payload_json",
                definition_sql="profile_payload_json TEXT NOT NULL DEFAULT '{}'",
            )
        except Exception as exc:
            LOGGER.warning("failed to add visitpsychcontext.profile_payload_json: %s", exc)
        conn.commit()


def get_db():
    with Session(engine) as session:
        yield session


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def create_token() -> str:
    return secrets.token_urlsafe(32)


def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)) -> UserRecord:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    token_row = db.get(AuthTokenRecord, token)
    if not token_row:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.get(UserRecord, token_row.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def call_llm(history, course, visit, visit_state, psych_context):
    return await get_psychagent_backend().reply_from_visit(
        fallback_messages=history,
        course=course,
        visit=visit,
        visit_state=visit_state,
        psych_context=psych_context,
    )


async def run_session_close_postprocess(course, visit, visit_state, psych_context):
    return await get_psychagent_backend().build_session_close_artifacts(
        course=course,
        visit=visit,
        visit_state=visit_state,
        psych_context=psych_context,
    )


app.include_router(create_courses_router(get_db, get_current_user, call_llm))
app.include_router(
    create_visits_router(
        get_db,
        get_current_user,
        call_llm,
        run_session_close_postprocess,
    )
)


@app.on_event("startup")
async def on_startup() -> None:
    configure_logging()
    SQLModel.metadata.create_all(engine)
    run_sqlite_migrations()
    await get_psychagent_backend().startup()
    LOGGER.info("PsychAgent web startup complete db=%s", DB_URL)


@app.get("/health")
def health():
    backend = get_psychagent_backend()
    return {
        "status": "ok",
        "baseline": str(backend.baseline_config.name),
        "model": backend.baseline_config.model,
        "runtime_output_language": backend.runtime_config.output_language,
    }


@app.post("/auth/register", response_model=AuthResponse)
def register(payload: AuthPayload, db: Session = Depends(get_db)):
    exists = db.exec(select(UserRecord).where(UserRecord.username == payload.username)).first()
    if exists:
        raise HTTPException(status_code=400, detail="用户已存在")
    user = UserRecord(username=payload.username, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    token_value = create_token()
    db.add(AuthTokenRecord(token=token_value, user_id=user.id))
    db.commit()
    return AuthResponse(
        token=token_value,
        user=UserOut(id=user.id, username=user.username, created_at=user.created_at),
    )


@app.post("/auth/login", response_model=AuthResponse)
def login(payload: AuthPayload, db: Session = Depends(get_db)):
    user = db.exec(select(UserRecord).where(UserRecord.username == payload.username)).first()
    if not user or user.password_hash != hash_password(payload.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token_value = create_token()
    db.add(AuthTokenRecord(token=token_value, user_id=user.id))
    db.commit()
    return AuthResponse(
        token=token_value,
        user=UserOut(id=user.id, username=user.username, created_at=user.created_at),
    )


@app.get("/schools", response_model=List[SchoolInfo])
def list_schools():
    return SCHOOLS


@app.get("/stages", response_model=List[StageInfo])
def list_stages():
    return [stage_from_key(key) for key in STAGES.keys()]
