from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from ..schemas import (
    CompleteCourseRequest,
    CourseDetail,
    CoursePreview,
    CreateCourseRequest,
    CreateCourseResponse,
    UpdateCourseRequest,
)
from ..services import course_service, visit_service


def create_courses_router(get_db_dep, get_current_user_dep, call_llm):
    router = APIRouter(tags=["courses"])

    @router.get("/courses", response_model=List[CoursePreview])
    def list_courses(
        school_id: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
        db=Depends(get_db_dep),
        user=Depends(get_current_user_dep),
    ):
        return course_service.list_courses(db, user.id, school_id=school_id, status=status)

    @router.post("/courses", response_model=CreateCourseResponse)
    async def create_course(
        payload: CreateCourseRequest,
        db=Depends(get_db_dep),
        user=Depends(get_current_user_dep),
    ):
        course = course_service.create_course(db, user.id, payload)
        created_visit = None
        if payload.auto_start_first_visit:
            created_visit = await visit_service.create_visit(
                db,
                user.id,
                course.course_id,
                opening_note=payload.opening_note,
                call_llm=call_llm,
            )
        return CreateCourseResponse(
            course=course_service.get_course_detail(db, user.id, course.course_id),
            created_visit=created_visit,
        )

    @router.get("/courses/{course_id}", response_model=CourseDetail)
    def get_course(course_id: str, db=Depends(get_db_dep), user=Depends(get_current_user_dep)):
        return course_service.get_course_detail(db, user.id, course_id)

    @router.patch("/courses/{course_id}", response_model=CourseDetail)
    def update_course(
        course_id: str,
        payload: UpdateCourseRequest,
        db=Depends(get_db_dep),
        user=Depends(get_current_user_dep),
    ):
        return course_service.update_course(db, user.id, course_id, payload)

    @router.post("/courses/{course_id}/complete", response_model=CourseDetail)
    def complete_course(
        course_id: str,
        payload: CompleteCourseRequest,
        db=Depends(get_db_dep),
        user=Depends(get_current_user_dep),
    ):
        return course_service.complete_course(db, user.id, course_id, payload.summary)

    @router.post("/courses/{course_id}/archive", response_model=CourseDetail)
    def archive_course(course_id: str, db=Depends(get_db_dep), user=Depends(get_current_user_dep)):
        return course_service.archive_course(db, user.id, course_id)

    return router
