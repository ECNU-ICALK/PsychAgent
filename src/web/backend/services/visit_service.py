from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..domain import pick_school, stage_from_key, summary_stage_to_stage_key
from ..models import (
    TherapyCourseRecord,
    TherapyVisitRecord,
    UserGlobalProfileRecord,
    VisitMessageRecord,
    VisitPsychContextRecord,
)
from ..schemas import (
    CloseVisitResponse,
    CourseMetaOut,
    SendVisitMessageResponse,
    VisitMessageOut,
    VisitPsychContextOut,
    VisitPreview,
    VisitState,
)
from .course_service import get_owned_course_record

CounselorReplyFn = Callable[
    [List[Dict[str, str]], TherapyCourseRecord, TherapyVisitRecord, VisitState, Optional[VisitPsychContextOut]],
    Awaitable[Any],
]
SessionClosePostprocessFn = Callable[
    [TherapyCourseRecord, TherapyVisitRecord, VisitState, Optional[VisitPsychContextOut]],
    Awaitable[Dict[str, Any]],
]

SESSION_FOCUS_DEFAULT = [
    "建立初始关系与咨询框架",
    "收集稳定背景信息",
    "了解当前主要困扰与近期变化",
    "澄清来访动机与期待",
    "进行基础身心与功能评估",
    "识别潜在风险与可用资源",
    "会谈总结与协作性反馈",
]

GLOBAL_STATIC_TRAIT_KEYS = [
    "name",
    "age",
    "gender",
    "occupation",
    "educational_background",
    "marital_status",
    "family_status",
    "social_status",
    "medical_history",
]

UNKNOWN_TEXT_VALUES = {"未知"}


def utcnow() -> datetime:
    return datetime.utcnow()


def build_visit_prompt(school, stage, visit_no: int, planned_visit_count: Optional[int]) -> str:
    if planned_visit_count:
        total_part = f"这是疗程中的第 {visit_no}/{planned_visit_count} 次会谈。"
    else:
        total_part = f"这是疗程中的第 {visit_no} 次会谈。"
    return (
        "你是一名专业心理咨询师，遵循伦理规范，提供共情、支持和结构化的对话。"
        f"当前流派：{school.name}。"
        f"当前阶段：{stage.label}（{stage.desc}）。"
        f"{total_part}"
        "保持简洁、温暖、尊重，避免给出医疗诊断或具体药物建议。"
    )


def build_opening_messages(
    course: TherapyCourseRecord,
    stage,
    visit_no: int,
    opening_note: str = "",
) -> List[VisitMessageRecord]:
    school = pick_school(course.school_id)
    now = utcnow()

    if visit_no == 1:
        assistant_text = (
            f"你好。我是你的{school.name}咨询师。今天是我们的第 {visit_no} 次会谈，属于{stage.label}阶段。"
            f"{school.desc}\n\n你今天想聊些什么？"
        )
    else:
        assistant_text = (
            f"欢迎回来。今天是我们的第 {visit_no} 次会谈，属于{stage.label}阶段。"
            "我们可以继续上次的工作，也可以先从你现在最在意的感受开始。"
        )

    if opening_note.strip():
        assistant_text = f"{assistant_text}\n\n本次关注：{opening_note.strip()}"

    return [
        VisitMessageRecord(
            visit_id="",
            role="system",
            text=f"第 {visit_no} 次会谈已开始。当前阶段：{stage.label}",
            created_at=now,
        ),
        VisitMessageRecord(
            visit_id="",
            role="assistant",
            text=assistant_text,
            created_at=now,
        ),
    ]


def build_opening_seed_user_text(visit_no: int, opening_note: str = "") -> str:
    base = f"这是第{visit_no}次会话"
    note = opening_note.strip()
    if not note:
        return base
    return f"{base}\n本次关注：{note}"


def _parse_assistant_payload(assistant_payload: Any) -> Tuple[str, bool]:
    should_auto_close = False
    if isinstance(assistant_payload, dict):
        assistant_text = str(assistant_payload.get("text") or "").strip()
        should_auto_close = bool(assistant_payload.get("end"))
    else:
        assistant_text = str(assistant_payload or "").strip()
    return assistant_text, should_auto_close


def _model_dump_compat(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    return dict(model)


def _build_opening_visit_state(visit_state: VisitState, seed_user_text: str) -> VisitState:
    seed_message = VisitMessageOut(
        id=f"seed-opening-{visit_state.visit_id}",
        role="user",
        text=seed_user_text,
        created_at=utcnow(),
    )
    payload = _model_dump_compat(visit_state)
    payload["messages"] = [*visit_state.messages, seed_message]
    return VisitState(**payload)


def get_owned_visit_and_course(db: Session, visit_id: str, user_id: str) -> Tuple[TherapyVisitRecord, TherapyCourseRecord]:
    visit = db.get(TherapyVisitRecord, visit_id)
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")

    course = db.get(TherapyCourseRecord, visit.course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return visit, course


def get_visit_messages(db: Session, visit_id: str) -> List[VisitMessageRecord]:
    return db.exec(
        select(VisitMessageRecord)
        .where(VisitMessageRecord.visit_id == visit_id)
        .order_by(VisitMessageRecord.created_at, VisitMessageRecord.id)
    ).all()


def _parse_json_dict(raw: str) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {}


def _parse_json_list(raw: str) -> List[Any]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass
    return []


def _normalize_text_list(raw: Any, limit: int = 8) -> List[str]:
    if not isinstance(raw, list):
        return []
    values: List[str] = []
    for item in raw:
        text = str(item).strip()
        if not text or text in values:
            continue
        values.append(text)
        if len(values) >= limit:
            break
    return values


def _normalize_static_traits(raw: Any) -> Dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    normalized: Dict[str, str] = {}
    for key in GLOBAL_STATIC_TRAIT_KEYS:
        value = str(raw.get(key) or "").strip()
        if value:
            normalized[key] = value
    return normalized


def _merge_static_traits(base: Any, override: Any) -> Dict[str, str]:
    base_traits = _normalize_static_traits(base)
    override_traits = _normalize_static_traits(override)
    merged: Dict[str, str] = dict(base_traits)
    for key, value in override_traits.items():
        if value and value not in UNKNOWN_TEXT_VALUES:
            merged[key] = value
    return merged


def _merge_global_base_profile(existing: Any, incoming: Any) -> Dict[str, Any]:
    existing_dict = dict(existing) if isinstance(existing, dict) else {}
    incoming_dict = dict(incoming) if isinstance(incoming, dict) else {}
    merged: Dict[str, Any] = {}

    static_traits = _merge_static_traits(
        existing_dict.get("static_traits"),
        incoming_dict.get("static_traits"),
    )
    if static_traits:
        merged["static_traits"] = static_traits

    existing_growth = _normalize_text_list(existing_dict.get("growth_experiences"), limit=20)
    incoming_growth = _normalize_text_list(incoming_dict.get("growth_experiences"), limit=20)
    if incoming_growth:
        merged["growth_experiences"] = incoming_growth
    elif existing_growth:
        merged["growth_experiences"] = existing_growth

    return merged


def _overlay_global_base_profile(course_profile: Any, global_base_profile: Any) -> Dict[str, Any]:
    profile = dict(course_profile) if isinstance(course_profile, dict) else {}
    global_base = dict(global_base_profile) if isinstance(global_base_profile, dict) else {}
    if not global_base:
        return profile

    profile["static_traits"] = _merge_static_traits(
        global_base.get("static_traits"),
        profile.get("static_traits"),
    )

    profile_growth = _normalize_text_list(profile.get("growth_experiences"), limit=20)
    global_growth = _normalize_text_list(global_base.get("growth_experiences"), limit=20)
    if profile_growth:
        profile["growth_experiences"] = profile_growth
    elif global_growth:
        profile["growth_experiences"] = global_growth

    return profile


def _extract_global_base_profile(client_info: Any) -> Dict[str, Any]:
    profile = dict(client_info) if isinstance(client_info, dict) else {}
    extracted: Dict[str, Any] = {}

    static_traits = _normalize_static_traits(profile.get("static_traits"))
    filtered_static_traits = {k: v for k, v in static_traits.items() if v not in UNKNOWN_TEXT_VALUES}
    if filtered_static_traits:
        extracted["static_traits"] = filtered_static_traits

    growth_experiences = _normalize_text_list(profile.get("growth_experiences"), limit=20)
    if growth_experiences:
        extracted["growth_experiences"] = growth_experiences

    return extracted


def get_user_global_base_profile(db: Session, user_id: str) -> Dict[str, Any]:
    record = db.get(UserGlobalProfileRecord, user_id)
    if not record:
        return {}
    return _parse_json_dict(record.base_profile_json)


def save_user_global_base_profile(
    db: Session,
    user_id: str,
    base_profile: Dict[str, Any],
    source: str = "profile_sync_v1",
) -> None:
    incoming = dict(base_profile) if isinstance(base_profile, dict) else {}
    if not incoming:
        return

    now = utcnow()
    record = db.get(UserGlobalProfileRecord, user_id)
    if not record:
        record = UserGlobalProfileRecord(
            user_id=user_id,
            created_at=now,
            updated_at=now,
        )
        existing = {}
    else:
        record.updated_at = now
        existing = _parse_json_dict(record.base_profile_json)

    merged = _merge_global_base_profile(existing, incoming)
    if not merged:
        return

    record.base_profile_json = json.dumps(merged, ensure_ascii=False)
    record.source = str(source or "profile_sync_v1")
    db.add(record)


def build_derived_psych_context_snapshot(
    db: Session,
    course: TherapyCourseRecord,
    visit: TherapyVisitRecord,
) -> Dict[str, Any]:
    previous_visit = db.exec(
        select(TherapyVisitRecord)
        .where(
            TherapyVisitRecord.course_id == course.course_id,
            TherapyVisitRecord.visit_no < visit.visit_no,
        )
        .order_by(TherapyVisitRecord.visit_no.desc())
    ).first()
    previous_context = (
        get_visit_psych_context_snapshot(db, previous_visit.visit_id) if previous_visit else None
    )

    if visit.visit_no <= 1:
        session_focus = list(SESSION_FOCUS_DEFAULT)
    else:
        planned_focus: List[str] = []
        if previous_context and isinstance(previous_context.client_info, dict):
            planned_focus = _normalize_text_list(
                previous_context.client_info.get("next_session_focus"),
                limit=8,
            )
        session_focus = planned_focus or (
            _normalize_text_list(previous_context.session_focus, limit=8) if previous_context else []
        )
        if not session_focus:
            session_focus = list(SESSION_FOCUS_DEFAULT)

    all_visits = db.exec(
        select(TherapyVisitRecord)
        .where(TherapyVisitRecord.course_id == course.course_id)
        .order_by(TherapyVisitRecord.visit_no)
    ).all()
    history: List[Dict[str, Any]] = []
    for item in all_visits:
        if item.visit_no >= visit.visit_no:
            continue
        stage = stage_from_key(item.stage_key_snapshot)
        item_context = get_visit_psych_context_snapshot(db, item.visit_id)
        summary_payload = (
            dict(item_context.summary_payload)
            if item_context and isinstance(item_context.summary_payload, dict)
            else {}
        )
        client_state_analysis = summary_payload.get("client_state_analysis")
        goal_assessment = summary_payload.get("goal_assessment")
        raw_homework = summary_payload.get("homework")
        homework = _normalize_text_list(raw_homework, limit=12) if isinstance(raw_homework, list) else []

        history_item: Dict[str, Any] = {
            "visit_id": item.visit_id,
            "visit_no": item.visit_no,
            "stage_key": item.stage_key_snapshot,
            "stage_label": stage.label,
            "session_stage": stage.label,
            "status": item.status,
            "summary": item.summary or "",
            "session_summary_abstract": str(summary_payload.get("session_summary_abstract") or item.summary or "").strip(),
            "message_count": item.message_count,
            "ended_at": item.ended_at.isoformat() if item.ended_at else None,
        }
        if summary_payload:
            history_item["summary_payload"] = summary_payload
        if isinstance(client_state_analysis, dict) and client_state_analysis:
            history_item["client_state_analysis"] = client_state_analysis
        if isinstance(goal_assessment, dict) and goal_assessment:
            history_item["goal_assessment"] = goal_assessment
        if homework:
            history_item["homework"] = homework
        history.append(history_item)

    school = pick_school(course.school_id)
    global_base_profile = get_user_global_base_profile(db, course.user_id)
    base_client_info = (
        dict(previous_context.client_info)
        if previous_context and isinstance(previous_context.client_info, dict)
        else {}
    )
    base_client_info = _overlay_global_base_profile(base_client_info, global_base_profile)
    client_info: Dict[str, Any] = {
        **base_client_info,
        "course_id": course.course_id,
        "school_id": school.id,
        "school_name": school.name,
        "school_style": school.style,
        "course_title": course.title,
        "goal_summary": course.goal_summary,
        "intake_note": course.intake_note,
        "course_summary": course.summary,
        "planned_visit_count": course.planned_visit_count,
        "latest_visit_no": course.latest_visit_no,
        "current_visit_no": visit.visit_no,
    }

    homework: List[str] = (
        _normalize_text_list(previous_context.homework, limit=12) if previous_context else []
    )

    return {
        "client_info": client_info,
        "session_focus": session_focus,
        "history": history,
        "homework": homework,
        "summary_payload": {},
        "profile_payload": {},
        "source": "derived_from_course_data_v2",
    }


def save_visit_psych_context_snapshot(
    db: Session,
    visit_id: str,
    snapshot: Dict[str, Any],
) -> None:
    now = utcnow()
    record = db.get(VisitPsychContextRecord, visit_id)
    if not record:
        record = VisitPsychContextRecord(
            visit_id=visit_id,
            created_at=now,
            updated_at=now,
        )
    else:
        record.updated_at = now

    client_info = snapshot.get("client_info")
    session_focus = snapshot.get("session_focus")
    history = snapshot.get("history")
    homework = snapshot.get("homework")
    summary_payload = snapshot.get("summary_payload")
    profile_payload = snapshot.get("profile_payload")

    record.client_info_json = json.dumps(client_info if isinstance(client_info, dict) else {}, ensure_ascii=False)
    record.session_focus_json = json.dumps(session_focus if isinstance(session_focus, list) else [], ensure_ascii=False)
    record.history_json = json.dumps(history if isinstance(history, list) else [], ensure_ascii=False)
    record.homework_json = json.dumps(homework if isinstance(homework, list) else [], ensure_ascii=False)
    record.summary_payload_json = json.dumps(
        summary_payload if isinstance(summary_payload, dict) else {},
        ensure_ascii=False,
    )
    record.profile_payload_json = json.dumps(
        profile_payload if isinstance(profile_payload, dict) else {},
        ensure_ascii=False,
    )
    record.source = str(snapshot.get("source", "derived_from_course_data_v1"))
    db.add(record)


def get_visit_psych_context_snapshot(db: Session, visit_id: str) -> Optional[VisitPsychContextOut]:
    record = db.get(VisitPsychContextRecord, visit_id)
    if not record:
        return None

    session_focus = [str(item).strip() for item in _parse_json_list(record.session_focus_json) if str(item).strip()]
    history = [item for item in _parse_json_list(record.history_json) if isinstance(item, dict)]
    homework = [str(item).strip() for item in _parse_json_list(record.homework_json) if str(item).strip()]
    summary_payload = _parse_json_dict(record.summary_payload_json)
    profile_payload = _parse_json_dict(record.profile_payload_json)

    return VisitPsychContextOut(
        client_info=_parse_json_dict(record.client_info_json),
        session_focus=session_focus,
        history=history,
        homework=homework,
        summary_payload=summary_payload,
        profile_payload=profile_payload,
        source=record.source,
        updated_at=record.updated_at,
    )


def build_visit_preview(visit: TherapyVisitRecord) -> VisitPreview:
    return VisitPreview(
        visit_id=visit.visit_id,
        visit_no=visit.visit_no,
        stage=stage_from_key(visit.stage_key_snapshot),
        status=visit.status,
        message_count=visit.message_count,
        started_at=visit.started_at,
        ended_at=visit.ended_at,
        summary=visit.summary,
    )


def build_visit_state(db: Session, visit: TherapyVisitRecord) -> VisitState:
    return VisitState(
        **build_visit_preview(visit).dict(),
        course_id=visit.course_id,
        messages=[
            VisitMessageOut(
                id=message.id,
                role=message.role,
                text=message.text,
                created_at=message.created_at,
            )
            for message in get_visit_messages(db, visit.visit_id)
        ],
        psych_context=get_visit_psych_context_snapshot(db, visit.visit_id),
    )


def list_visits(db: Session, user_id: str, course_id: str) -> List[VisitPreview]:
    course = get_owned_course_record(db, course_id, user_id)
    visits = db.exec(
        select(TherapyVisitRecord)
        .where(TherapyVisitRecord.course_id == course.course_id)
        .order_by(TherapyVisitRecord.visit_no)
    ).all()
    return [build_visit_preview(visit) for visit in visits]


def resolve_stage_for_new_visit(db: Session, course: TherapyCourseRecord, next_visit_no: int):
    if next_visit_no <= 1:
        return stage_from_key("assessment")

    previous_visit = db.exec(
        select(TherapyVisitRecord)
        .where(
            TherapyVisitRecord.course_id == course.course_id,
            TherapyVisitRecord.visit_no < next_visit_no,
        )
        .order_by(TherapyVisitRecord.visit_no.desc())
    ).first()
    if not previous_visit:
        return stage_from_key("assessment")

    previous_context = get_visit_psych_context_snapshot(db, previous_visit.visit_id)
    if previous_context and isinstance(previous_context.client_info, dict):
        client_info = dict(previous_context.client_info)
        preferred_stage_key = str(client_info.get("next_session_stage_key") or "").strip()
        if preferred_stage_key:
            try:
                return stage_from_key(preferred_stage_key)
            except Exception:
                pass

        preferred_stage = str(client_info.get("next_session_stage") or "").strip()
        mapped_stage_key = summary_stage_to_stage_key(preferred_stage)
        if mapped_stage_key:
            return stage_from_key(mapped_stage_key)

    if previous_visit.stage_key_snapshot:
        try:
            return stage_from_key(previous_visit.stage_key_snapshot)
        except Exception:
            pass

    return stage_from_key("assessment")


async def create_visit(
    db: Session,
    user_id: str,
    course_id: str,
    opening_note: str = "",
    call_llm: Optional[CounselorReplyFn] = None,
) -> VisitState:
    course = get_owned_course_record(db, course_id, user_id)
    if course.status != "active":
        raise HTTPException(status_code=409, detail="只有进行中的疗程才能开始新会谈")

    open_visit = db.exec(
        select(TherapyVisitRecord).where(
            TherapyVisitRecord.course_id == course.course_id,
            TherapyVisitRecord.status == "open",
        )
    ).first()
    if open_visit:
        raise HTTPException(status_code=409, detail="当前疗程已有未结束的会谈")

    next_visit_no = course.latest_visit_no + 1
    stage = resolve_stage_for_new_visit(db, course, next_visit_no)
    now = utcnow()
    visit = TherapyVisitRecord(
        course_id=course.course_id,
        visit_no=next_visit_no,
        stage_key_snapshot=stage.key,
        status="open",
        started_at=now,
        ended_at=None,
        summary="",
        message_count=0,
        created_at=now,
        updated_at=now,
        legacy_session_id=None,
    )
    db.add(visit)
    db.flush()

    opening_messages = build_opening_messages(course, stage, next_visit_no, opening_note)
    system_opening_message = opening_messages[0]
    system_opening_message.visit_id = visit.visit_id
    db.add(system_opening_message)
    fallback_assistant_text = opening_messages[1].text if len(opening_messages) > 1 else ""

    visit.message_count = 1
    course.latest_visit_no = next_visit_no
    course.active_visit_id = visit.visit_id
    course.current_stage_key = stage.key
    course.last_message_at = now
    course.updated_at = now

    snapshot = build_derived_psych_context_snapshot(db, course, visit)
    save_visit_psych_context_snapshot(db, visit.visit_id, snapshot)
    db.flush()

    assistant_text = fallback_assistant_text
    if call_llm is not None:
        seed_user_text = build_opening_seed_user_text(next_visit_no, opening_note)
        opening_history: List[Dict[str, str]] = [
            {
                "role": "system",
                "content": build_visit_prompt(
                    pick_school(course.school_id),
                    stage,
                    visit.visit_no,
                    course.planned_visit_count,
                ),
            },
            {"role": "user", "content": seed_user_text},
        ]
        opening_visit_state = _build_opening_visit_state(build_visit_state(db, visit), seed_user_text)
        try:
            assistant_payload = await call_llm(
                opening_history,
                course,
                visit,
                opening_visit_state,
                opening_visit_state.psych_context,
            )
            generated_text, _ = _parse_assistant_payload(assistant_payload)
            if generated_text:
                assistant_text = generated_text
        except Exception:
            assistant_text = fallback_assistant_text

    assistant_text = str(assistant_text or "").strip()
    if not assistant_text:
        db.rollback()
        raise HTTPException(status_code=502, detail="会谈开场生成失败，请稍后重试")

    now = utcnow()
    opening_assistant_message = VisitMessageRecord(
        visit_id=visit.visit_id,
        role="assistant",
        text=assistant_text,
        created_at=now,
    )
    visit.updated_at = now
    visit.message_count += 1
    course.updated_at = now
    course.last_message_at = now
    db.add_all([opening_assistant_message, visit, course])
    snapshot = build_derived_psych_context_snapshot(db, course, visit)
    save_visit_psych_context_snapshot(db, visit.visit_id, snapshot)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="当前疗程已有未结束的会谈") from None
    db.refresh(visit)
    return build_visit_state(db, visit)


def get_visit_state_for_user(db: Session, user_id: str, visit_id: str) -> VisitState:
    visit, _course = get_owned_visit_and_course(db, visit_id, user_id)
    return build_visit_state(db, visit)


async def send_visit_message(
    db: Session,
    user_id: str,
    visit_id: str,
    text: str,
    call_llm: CounselorReplyFn,
    run_session_close_postprocess: Optional[SessionClosePostprocessFn] = None,
) -> SendVisitMessageResponse:
    visit, course = get_owned_visit_and_course(db, visit_id, user_id)
    if visit.status != "open":
        raise HTTPException(status_code=409, detail="当前会谈已结束，无法继续发送消息")

    now = utcnow()
    user_message = VisitMessageRecord(
        visit_id=visit.visit_id,
        role="user",
        text=text,
        created_at=now,
    )
    visit.updated_at = now
    visit.message_count += 1
    course.updated_at = now
    course.last_message_at = now
    db.add_all([user_message, visit, course])
    db.flush()

    visit_state_after_user = build_visit_state(db, visit)
    stage = stage_from_key(visit.stage_key_snapshot)
    school = pick_school(course.school_id)

    history: List[Dict[str, str]] = [{"role": "system", "content": build_visit_prompt(
        school,
        stage,
        visit.visit_no,
        course.planned_visit_count,
    )}]
    for message in visit_state_after_user.messages:
        history.append({"role": message.role, "content": message.text})
    try:
        assistant_payload = await call_llm(
            history,
            course,
            visit,
            visit_state_after_user,
            visit_state_after_user.psych_context,
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail="大模型调用失败，请稍后重试") from exc

    assistant_text, should_auto_close = _parse_assistant_payload(assistant_payload)
    if not assistant_text:
        db.rollback()
        raise HTTPException(status_code=502, detail="大模型返回为空，请稍后重试")

    now = utcnow()
    assistant_message = VisitMessageRecord(
        visit_id=visit.visit_id,
        role="assistant",
        text=assistant_text,
        created_at=now,
    )
    visit.updated_at = now
    visit.message_count += 1
    course.updated_at = now
    course.last_message_at = now
    db.add_all([assistant_message, visit, course])
    snapshot = build_derived_psych_context_snapshot(db, course, visit)
    save_visit_psych_context_snapshot(db, visit.visit_id, snapshot)

    if should_auto_close:
        db.flush()
        await close_visit(
            db,
            user_id,
            visit.visit_id,
            summary="",
            run_session_close_postprocess=run_session_close_postprocess,
        )
        db.refresh(visit)
        db.refresh(course)
    else:
        db.commit()
        db.refresh(visit)
        db.refresh(course)

    return SendVisitMessageResponse(
        visit=build_visit_state(db, visit),
        course_meta=CourseMetaOut(
            course_id=course.course_id,
            last_message_at=course.last_message_at,
            updated_at=course.updated_at,
        ),
    )


async def close_visit(
    db: Session,
    user_id: str,
    visit_id: str,
    summary: str = "",
    run_session_close_postprocess: Optional[SessionClosePostprocessFn] = None,
) -> CloseVisitResponse:
    visit, course = get_owned_visit_and_course(db, visit_id, user_id)
    if visit.status != "open":
        raise HTTPException(status_code=409, detail="当前会谈已结束")

    visit_state_before_close = build_visit_state(db, visit)
    close_artifacts: Dict[str, Any] = {}
    if run_session_close_postprocess is not None:
        try:
            close_artifacts = await run_session_close_postprocess(
                course,
                visit,
                visit_state_before_close,
                visit_state_before_close.psych_context,
            )
        except Exception:
            close_artifacts = {}

    resolved_summary = summary.strip()
    if not resolved_summary:
        resolved_summary = str(close_artifacts.get("summary_text") or "").strip()

    now = utcnow()
    closing_message = VisitMessageRecord(
        visit_id=visit.visit_id,
        role="system",
        text="--- 本次会谈已结束，进度已保存 ---",
        created_at=now,
    )
    visit.status = "closed"
    visit.ended_at = now
    visit.summary = resolved_summary
    visit.updated_at = now
    visit.message_count += 1
    course.active_visit_id = None
    course.updated_at = now
    course.last_message_at = now
    db.add_all([closing_message, visit, course])
    snapshot = build_derived_psych_context_snapshot(db, course, visit)
    snapshot["summary_payload"] = {}
    snapshot["profile_payload"] = {}
    merged_client_info = dict(snapshot.get("client_info") or {})
    updated_profile = close_artifacts.get("updated_profile")
    if isinstance(updated_profile, dict):
        merged_client_info.update(updated_profile)

    next_stage_key = str(close_artifacts.get("next_session_stage_key") or "").strip()
    should_complete_course = bool(close_artifacts.get("should_complete_course"))
    if next_stage_key:
        merged_client_info["next_session_stage_key"] = next_stage_key

    next_stage_label = str(close_artifacts.get("next_session_stage") or "").strip()
    if next_stage_label:
        merged_client_info["next_session_stage"] = next_stage_label
    elif next_stage_key:
        try:
            merged_client_info["next_session_stage"] = stage_from_key(next_stage_key).label
        except Exception:
            pass

    snapshot["client_info"] = merged_client_info

    next_focus = _normalize_text_list(close_artifacts.get("next_session_focus"), limit=8)
    if next_focus:
        merged_client_info["next_session_focus"] = next_focus
    else:
        merged_client_info.pop("next_session_focus", None)

    next_homework = _normalize_text_list(close_artifacts.get("homework"), limit=12)
    if next_homework:
        snapshot["homework"] = next_homework

    summary_payload = close_artifacts.get("summary_payload")
    if isinstance(summary_payload, dict):
        snapshot["summary_payload"] = summary_payload

    profile_payload = close_artifacts.get("profile_payload")
    if not isinstance(profile_payload, dict):
        profile_payload = updated_profile if isinstance(updated_profile, dict) else {}
    if profile_payload:
        snapshot["profile_payload"] = profile_payload

    global_base_profile = _extract_global_base_profile(merged_client_info)
    if global_base_profile:
        save_user_global_base_profile(
            db=db,
            user_id=course.user_id,
            base_profile=global_base_profile,
            source=str(close_artifacts.get("source") or "profile_sync_v1"),
        )

    if should_complete_course:
        course.status = "completed"
        course.active_visit_id = None
        merged_client_info.pop("next_session_stage_key", None)
        merged_client_info["next_session_stage"] = "Termination"
        merged_client_info.pop("next_session_focus", None)
        if resolved_summary and not str(course.summary or "").strip():
            course.summary = resolved_summary

    source = str(close_artifacts.get("source") or "").strip()
    if source:
        snapshot["source"] = source
    save_visit_psych_context_snapshot(db, visit.visit_id, snapshot)
    db.commit()
    db.refresh(visit)

    return CloseVisitResponse(
        visit_id=visit.visit_id,
        status=visit.status,
        ended_at=visit.ended_at,
        summary=visit.summary,
    )
