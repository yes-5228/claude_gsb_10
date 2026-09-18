"""节假日 / 重大活动保障值守接口。"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import PaginationDep, build_meta
from app.core.constants import AssuranceStatus
from app.core.database import get_db
from app.schemas.assurance import (
    AssuranceAction,
    AssuranceCreate,
    AssuranceDetail,
    AssuranceDutyOut,
    AssuranceDutyUpdate,
    AssuranceOut,
    AssuranceSummary,
    AssuranceUpdate,
    RelinkOut,
)
from app.schemas.common import MessageOut, Page
from app.services import assurance_service

router = APIRouter(prefix="/assurances", tags=["保障值守"])


@router.get("", response_model=Page[AssuranceOut], summary="保障列表")
def list_assurances(
    db: Annotated[Session, Depends(get_db)],
    pagination: PaginationDep,
    status: Annotated[str | None, Query(description="保障状态")] = None,
    level: Annotated[str | None, Query(description="保障等级")] = None,
    assurance_type: Annotated[str | None, Query(description="保障类型")] = None,
    keyword: Annotated[str | None, Query(description="名称/编号/联络人模糊搜索")] = None,
    active_on: Annotated[date | None, Query(description="查询该日期处于保障时段内的保障")] = None,
    sort_by: Annotated[str, Query(description="排序字段")] = "start_date",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> Page[AssuranceOut]:
    rows, total = assurance_service.list_assurances(
        db,
        status=status,
        level=level,
        assurance_type=assurance_type,
        keyword=keyword,
        active_on=active_on,
        page=pagination.page,
        page_size=pagination.page_size,
        sort_by=sort_by,
        order=order,
    )
    return Page[AssuranceOut](
        items=[assurance_service.to_out(row) for row in rows],
        meta=build_meta(total, pagination),
    )


@router.post("", response_model=AssuranceDetail, status_code=201, summary="新增保障并自动排班")
def create_assurance(payload: AssuranceCreate, db: Annotated[Session, Depends(get_db)]) -> AssuranceDetail:
    assurance = assurance_service.create_assurance(db, payload)
    return assurance_service.to_detail(db, assurance)


@router.get("/{assurance_id}", response_model=AssuranceDetail, summary="保障详情")
def get_assurance(
    assurance_id: int, db: Annotated[Session, Depends(get_db)]
) -> AssuranceDetail:
    return assurance_service.to_detail(db, assurance_service.get_assurance(db, assurance_id))


@router.patch("/{assurance_id}", response_model=AssuranceDetail, summary="更新保障")
def update_assurance(
    assurance_id: int, payload: AssuranceUpdate, db: Annotated[Session, Depends(get_db)]
) -> AssuranceDetail:
    assurance = assurance_service.update_assurance(db, assurance_id, payload)
    return assurance_service.to_detail(db, assurance)


@router.delete("/{assurance_id}", response_model=MessageOut, summary="删除保障")
def delete_assurance(
    assurance_id: int,
    db: Annotated[Session, Depends(get_db)],
    force: Annotated[bool, Query(description="为 true 时解除问题归属后删除")] = False,
) -> MessageOut:
    assurance_service.delete_assurance(db, assurance_id, force=force)
    return MessageOut(message="删除成功")


@router.post("/{assurance_id}/start", response_model=AssuranceDetail, summary="启动保障")
def start_assurance(
    assurance_id: int, payload: AssuranceAction, db: Annotated[Session, Depends(get_db)]
) -> AssuranceDetail:
    assurance = assurance_service.change_status(db, assurance_id, AssuranceStatus.ACTIVE, payload)
    return assurance_service.to_detail(db, assurance)


@router.post("/{assurance_id}/finish", response_model=AssuranceDetail, summary="结束保障并生成小结")
def finish_assurance(
    assurance_id: int, payload: AssuranceAction, db: Annotated[Session, Depends(get_db)]
) -> AssuranceDetail:
    assurance = assurance_service.change_status(db, assurance_id, AssuranceStatus.FINISHED, payload)
    return assurance_service.to_detail(db, assurance)


@router.post("/{assurance_id}/cancel", response_model=AssuranceDetail, summary="取消/终止保障")
def cancel_assurance(
    assurance_id: int, payload: AssuranceAction, db: Annotated[Session, Depends(get_db)]
) -> AssuranceDetail:
    assurance = assurance_service.change_status(db, assurance_id, AssuranceStatus.CANCELLED, payload)
    return assurance_service.to_detail(db, assurance)


@router.get("/{assurance_id}/duties", response_model=Page[AssuranceDutyOut], summary="值守安排")
def list_duties(
    assurance_id: int,
    db: Annotated[Session, Depends(get_db)],
    pagination: PaginationDep,
    duty_date: Annotated[date | None, Query(description="按值守日期过滤")] = None,
    shift: Annotated[str | None, Query(description="按班次过滤")] = None,
    restroom_id: Annotated[int | None, Query(description="按公厕过滤")] = None,
    assignee: Annotated[str | None, Query(description="按值守人模糊过滤")] = None,
) -> Page[AssuranceDutyOut]:
    assurance_service.get_assurance(db, assurance_id)
    rows, total, counts = assurance_service.list_duties(
        db,
        assurance_id,
        duty_date=duty_date,
        shift=shift,
        restroom_id=restroom_id,
        assignee=assignee,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return Page[AssuranceDutyOut](
        items=assurance_service.duty_page_to_out(rows, counts),
        meta=build_meta(total, pagination),
    )


@router.patch(
    "/{assurance_id}/duties/{duty_id}", response_model=AssuranceDutyOut, summary="改派值守岗位"
)
def update_duty(
    assurance_id: int,
    duty_id: int,
    payload: AssuranceDutyUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> AssuranceDutyOut:
    assurance = assurance_service.get_assurance(db, assurance_id)
    duty = assurance_service.update_duty(db, assurance_id, duty_id, payload)
    return assurance_service.get_duty_out(db, assurance, duty)


@router.post(
    "/{assurance_id}/duties/regenerate", response_model=AssuranceDetail, summary="重新自动排班"
)
def regenerate_duties(
    assurance_id: int, db: Annotated[Session, Depends(get_db)]
) -> AssuranceDetail:
    assurance = assurance_service.regenerate_duties(db, assurance_id)
    return assurance_service.to_detail(db, assurance)


@router.post(
    "/{assurance_id}/relink-issues", response_model=RelinkOut, summary="归集保障期未归属问题"
)
def relink_issues(assurance_id: int, db: Annotated[Session, Depends(get_db)]) -> RelinkOut:
    return RelinkOut(relinked=assurance_service.relink_issues(db, assurance_id))


@router.get("/{assurance_id}/summary", response_model=AssuranceSummary, summary="保障情况小结（实时）")
def get_summary(
    assurance_id: int, db: Annotated[Session, Depends(get_db)]
) -> AssuranceSummary:
    assurance = assurance_service.get_assurance(db, assurance_id)
    return assurance_service.build_summary(db, assurance, persist=False)


@router.post(
    "/{assurance_id}/summary/refresh", response_model=AssuranceDetail, summary="刷新并归档小结"
)
def refresh_summary(
    assurance_id: int, db: Annotated[Session, Depends(get_db)]
) -> AssuranceDetail:
    assurance = assurance_service.refresh_summary(db, assurance_id)
    return assurance_service.to_detail(db, assurance)
