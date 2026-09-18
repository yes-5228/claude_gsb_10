"""节假日与重大活动保障接口。"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import PaginationDep, build_meta
from app.core.database import get_db
from app.schemas.common import MessageOut, Page
from app.schemas.issue import IssueOut
from app.schemas.support import (
    SupportDutyOut,
    SupportPlanCreate,
    SupportPlanDetail,
    SupportPlanOut,
    SupportPlanUpdate,
    SupportSummary,
)
from app.services import issue_service, support_service

router = APIRouter(prefix="/support-plans", tags=["保障管理"])


@router.get("", response_model=Page[SupportPlanOut], summary="保障方案列表")
def list_plans(
    db: Annotated[Session, Depends(get_db)],
    pagination: PaginationDep,
    keyword: Annotated[str | None, Query(description="名称/编号/要求模糊搜索")] = None,
    category: Annotated[str | None, Query(description="保障类型")] = None,
    level: Annotated[str | None, Query(description="保障等级")] = None,
    status: Annotated[str | None, Query(description="保障状态")] = None,
    date_from: Annotated[date | None, Query(description="保障结束日期不早于该日")] = None,
    date_to: Annotated[date | None, Query(description="保障开始日期不晚于该日")] = None,
    sort_by: Annotated[str, Query(description="排序字段")] = "created_at",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> Page[SupportPlanOut]:
    rows, total = support_service.list_plans(
        db,
        keyword=keyword,
        category=category,
        level=level,
        status=status,
        date_from=date_from,
        date_to=date_to,
        page=pagination.page,
        page_size=pagination.page_size,
        sort_by=sort_by,
        order=order,
    )
    return Page[SupportPlanOut](
        items=[support_service.to_out(db, row) for row in rows],
        meta=build_meta(total, pagination),
    )


@router.post("", response_model=SupportPlanOut, status_code=201, summary="新增保障方案")
def create_plan(
    payload: SupportPlanCreate, db: Annotated[Session, Depends(get_db)]
) -> SupportPlanOut:
    return support_service.to_out(db, support_service.create_plan(db, payload))


@router.get("/{plan_id}", response_model=SupportPlanDetail, summary="保障方案详情")
def get_plan(plan_id: int, db: Annotated[Session, Depends(get_db)]) -> SupportPlanDetail:
    return support_service.to_detail(db, support_service.get_plan(db, plan_id))


@router.patch("/{plan_id}", response_model=SupportPlanOut, summary="更新保障方案")
def update_plan(
    plan_id: int, payload: SupportPlanUpdate, db: Annotated[Session, Depends(get_db)]
) -> SupportPlanOut:
    return support_service.to_out(db, support_service.update_plan(db, plan_id, payload))


@router.delete("/{plan_id}", response_model=MessageOut, summary="删除保障方案")
def delete_plan(plan_id: int, db: Annotated[Session, Depends(get_db)]) -> MessageOut:
    support_service.delete_plan(db, plan_id)
    return MessageOut(message="删除成功")


@router.post("/{plan_id}/activate", response_model=SupportPlanDetail, summary="启动保障")
def activate_plan(plan_id: int, db: Annotated[Session, Depends(get_db)]) -> SupportPlanDetail:
    plan = support_service.activate_plan(db, plan_id)
    return support_service.to_detail(db, plan)


@router.post("/{plan_id}/finish", response_model=SupportPlanDetail, summary="结束保障")
def finish_plan(plan_id: int, db: Annotated[Session, Depends(get_db)]) -> SupportPlanDetail:
    plan = support_service.finish_plan(db, plan_id)
    return support_service.to_detail(db, plan)


@router.post(
    "/{plan_id}/duties/generate",
    response_model=list[SupportDutyOut],
    summary="按等级重新生成值守安排",
)
def generate_duties(plan_id: int, db: Annotated[Session, Depends(get_db)]) -> list[SupportDutyOut]:
    plan = support_service.get_plan(db, plan_id)
    duties = support_service.generate_duties(db, plan)
    return [SupportDutyOut.model_validate(duty) for duty in duties]


@router.get("/{plan_id}/issues", response_model=Page[IssueOut], summary="保障期间问题汇总")
def list_plan_issues(
    plan_id: int,
    db: Annotated[Session, Depends(get_db)],
    pagination: PaginationDep,
) -> Page[IssueOut]:
    plan = support_service.get_plan(db, plan_id)
    rows, total = support_service.plan_issues(
        db, plan, page=pagination.page, page_size=pagination.page_size
    )
    return Page[IssueOut](
        items=[issue_service.to_out(issue) for issue in rows],
        meta=build_meta(total, pagination),
    )


@router.get("/{plan_id}/summary", response_model=SupportSummary, summary="保障情况小结")
def get_plan_summary(plan_id: int, db: Annotated[Session, Depends(get_db)]) -> SupportSummary:
    plan = support_service.get_plan(db, plan_id)
    return support_service.build_summary(db, plan)
