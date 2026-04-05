from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, delete, select

from ..domain import pick_school, stage_from_key
from ..models import CourseGoalRecord, TherapyCourseRecord, TherapyVisitRecord
from ..schemas import CourseDetail, CourseGoalOut, CoursePreview, CourseStats


def utcnow() -> datetime:
    return datetime.utcnow()


def build_default_course_title(school_name: str, created_at: datetime) -> str:
    return f"{school_name} 疗程 {created_at.strftime('%Y-%m-%d')}"


def get_owned_course_record(db: Session, course_id: str, user_id: str) -> TherapyCourseRecord:
    course = db.get(TherapyCourseRecord, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return course


def get_user_active_course(
    db: Session,
    user_id: str,
    exclude_course_id: Optional[str] = None,
) -> Optional[TherapyCourseRecord]:
    query = select(TherapyCourseRecord).where(
        TherapyCourseRecord.user_id == user_id,
        TherapyCourseRecord.status == "active",
    )
    if exclude_course_id:
        query = query.where(TherapyCourseRecord.course_id != exclude_course_id)
    return db.exec(
        query.order_by(TherapyCourseRecord.updated_at.desc(), TherapyCourseRecord.created_at.desc())
    ).first()


def format_course_identity(course: TherapyCourseRecord) -> str:
    try:
        school_name = pick_school(course.school_id).name
    except Exception:
        school_name = course.school_id or "未知流派"
    title = str(course.title or "").strip() or "未命名疗程"
    return f"{school_name} / {title}"


def get_course_goals(db: Session, course_id: str) -> List[CourseGoalRecord]:
    return db.exec(
        select(CourseGoalRecord)
        .where(CourseGoalRecord.course_id == course_id)
        .order_by(CourseGoalRecord.sort_order, CourseGoalRecord.created_at)
    ).all()


def get_course_visits(db: Session, course_id: str) -> List[TherapyVisitRecord]:
    return db.exec(
        select(TherapyVisitRecord)
        .where(TherapyVisitRecord.course_id == course_id)
        .order_by(TherapyVisitRecord.visit_no)
    ).all()


def build_course_preview(course: TherapyCourseRecord) -> CoursePreview:
    return CoursePreview(
        course_id=course.course_id,
        school=pick_school(course.school_id),
        title=course.title,
        status=course.status,
        current_stage=stage_from_key(course.current_stage_key),
        latest_visit_no=course.latest_visit_no,
        active_visit_id=course.active_visit_id,
        planned_visit_count=course.planned_visit_count,
        goal_summary=course.goal_summary,
        summary=course.summary,
        updated_at=course.updated_at,
        created_at=course.created_at,
    )


def build_course_detail(db: Session, course: TherapyCourseRecord) -> CourseDetail:
    goals = get_course_goals(db, course.course_id)
    visits = get_course_visits(db, course.course_id)

    return CourseDetail(
        **build_course_preview(course).dict(),
        intake_note=course.intake_note,
        goals=[
            CourseGoalOut(
                goal_id=goal.goal_id,
                content=goal.content,
                sort_order=goal.sort_order,
                status=goal.status,
            )
            for goal in goals
        ],
        stats=CourseStats(
            visit_count=len(visits),
            closed_visit_count=sum(1 for visit in visits if visit.status == "closed"),
            message_count=sum(visit.message_count for visit in visits),
        ),
    )


def list_courses(
    db: Session,
    user_id: str,
    school_id: Optional[str] = None,
    status: Optional[str] = None,
) -> List[CoursePreview]:
    query = select(TherapyCourseRecord).where(TherapyCourseRecord.user_id == user_id)
    if school_id:
        query = query.where(TherapyCourseRecord.school_id == school_id)
    if status:
        query = query.where(TherapyCourseRecord.status == status)

    courses = db.exec(query.order_by(TherapyCourseRecord.updated_at.desc())).all()
    return [build_course_preview(course) for course in courses]


def create_course(db: Session, user_id: str, payload) -> TherapyCourseRecord:
    school = pick_school(payload.school_id)
    now = utcnow()
    course = TherapyCourseRecord(
        user_id=user_id,
        school_id=payload.school_id,
        title=(payload.title or "").strip() or build_default_course_title(school.name, now),
        status="active",
        current_stage_key="assessment",
        planned_visit_count=payload.planned_visit_count,
        latest_visit_no=0,
        active_visit_id=None,
        goal_summary=(payload.goal_summary or "").strip(),
        intake_note=(payload.intake_note or "").strip(),
        summary="",
        last_message_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(course)
    db.flush()

    for index, content in enumerate(payload.goals):
        text = content.strip()
        if not text:
            continue
        db.add(
            CourseGoalRecord(
                course_id=course.course_id,
                content=text,
                sort_order=index,
                status="active",
                created_at=now,
                updated_at=now,
            )
        )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="创建疗程失败，请稍后重试。",
        ) from None
    db.refresh(course)
    return course


def get_course_detail(db: Session, user_id: str, course_id: str) -> CourseDetail:
    course = get_owned_course_record(db, course_id, user_id)
    return build_course_detail(db, course)


def update_course(db: Session, user_id: str, course_id: str, payload) -> CourseDetail:
    course = get_owned_course_record(db, course_id, user_id)
    now = utcnow()

    if payload.title is not None:
        school = pick_school(course.school_id)
        course.title = payload.title.strip() or build_default_course_title(school.name, course.created_at)
    if payload.planned_visit_count is not None:
        course.planned_visit_count = payload.planned_visit_count
    if payload.goal_summary is not None:
        course.goal_summary = payload.goal_summary.strip()
    if payload.intake_note is not None:
        course.intake_note = payload.intake_note.strip()
    if payload.summary is not None:
        course.summary = payload.summary.strip()

    if payload.goals is not None:
        db.exec(delete(CourseGoalRecord).where(CourseGoalRecord.course_id == course.course_id))
        for index, content in enumerate(payload.goals):
            text = content.strip()
            if not text:
                continue
            db.add(
                CourseGoalRecord(
                    course_id=course.course_id,
                    content=text,
                    sort_order=index,
                    status="active",
                    created_at=now,
                    updated_at=now,
                )
            )

    course.updated_at = now
    db.add(course)
    db.commit()
    db.refresh(course)
    return build_course_detail(db, course)


def complete_course(db: Session, user_id: str, course_id: str, summary: str = "") -> CourseDetail:
    course = get_owned_course_record(db, course_id, user_id)
    open_visit = db.exec(
        select(TherapyVisitRecord).where(
            TherapyVisitRecord.course_id == course.course_id,
            TherapyVisitRecord.status == "open",
        )
    ).first()
    if open_visit:
        raise HTTPException(status_code=409, detail="请先结束当前会谈，再完成疗程")

    course.status = "completed"
    course.active_visit_id = None
    if summary.strip():
        course.summary = summary.strip()
    course.updated_at = utcnow()
    db.add(course)
    db.commit()
    db.refresh(course)
    return build_course_detail(db, course)


def archive_course(db: Session, user_id: str, course_id: str) -> CourseDetail:
    course = get_owned_course_record(db, course_id, user_id)
    if course.status != "completed":
        raise HTTPException(status_code=409, detail="只有已完成的疗程才能归档")

    course.status = "archived"
    course.updated_at = utcnow()
    db.add(course)
    db.commit()
    db.refresh(course)
    return build_course_detail(db, course)
