from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends

from ..schemas import (
    CloseVisitRequest,
    CloseVisitResponse,
    CreateVisitRequest,
    SendVisitMessageRequest,
    SendVisitMessageResponse,
    VisitPreview,
    VisitState,
)
from ..services import visit_service


def create_visits_router(get_db_dep, get_current_user_dep, call_llm, run_session_close_postprocess):
    router = APIRouter(tags=["visits"])

    @router.get("/courses/{course_id}/visits", response_model=List[VisitPreview])
    def list_visits(course_id: str, db=Depends(get_db_dep), user=Depends(get_current_user_dep)):
        return visit_service.list_visits(db, user.id, course_id)

    @router.post("/courses/{course_id}/visits", response_model=VisitState)
    async def create_visit(
        course_id: str,
        payload: CreateVisitRequest,
        db=Depends(get_db_dep),
        user=Depends(get_current_user_dep),
    ):
        return await visit_service.create_visit(
            db,
            user.id,
            course_id,
            opening_note=payload.opening_note,
            call_llm=call_llm,
        )

    @router.get("/visits/{visit_id}", response_model=VisitState)
    def get_visit(visit_id: str, db=Depends(get_db_dep), user=Depends(get_current_user_dep)):
        return visit_service.get_visit_state_for_user(db, user.id, visit_id)

    @router.post("/visits/{visit_id}/messages", response_model=SendVisitMessageResponse)
    async def send_visit_message(
        visit_id: str,
        payload: SendVisitMessageRequest,
        db=Depends(get_db_dep),
        user=Depends(get_current_user_dep),
    ):
        return await visit_service.send_visit_message(
            db,
            user.id,
            visit_id,
            payload.text,
            call_llm,
            run_session_close_postprocess=run_session_close_postprocess,
        )

    @router.post("/visits/{visit_id}/close", response_model=CloseVisitResponse)
    async def close_visit(
        visit_id: str,
        payload: CloseVisitRequest,
        db=Depends(get_db_dep),
        user=Depends(get_current_user_dep),
    ):
        return await visit_service.close_visit(
            db,
            user.id,
            visit_id,
            payload.summary,
            run_session_close_postprocess=run_session_close_postprocess,
        )

    return router
