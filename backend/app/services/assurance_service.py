"""节假日 / 重大活动保障值守业务逻辑。"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import (
    ASSURANCE_ACTIVE_STATUSES,
    ASSURANCE_DAILY_MIN,
    ASSURANCE_LEVEL_RANK,
    ASSURANCE_SHIFT_ORDER,
    ASSURANCE_SHIFT_PLAN,
    ASSURANCE_TRANSITION_ACTIONS,
    ASSURANCE_TRANSITIONS,
    OPEN_ISSUE_STATUSES,
    TARGET_SOURCE_DISTRICT,
    TARGET_SOURCE_MANUAL,
    AssuranceLevel,
    AssuranceStatus,
    IssueCategory,
    IssueSeverity,
    IssueStatus,
    RestroomStatus,
)
from app.core.exceptions import ConflictError, DomainError, NotFoundError
from app.models import (
    Assurance,
    AssuranceDuty,
    AssuranceTarget,
    Inspection,
    Issue,
    Restroom,
)
from app.schemas.assurance import (
    AssuranceAction,
    AssuranceCreate,
    AssuranceDetail,
    AssuranceDutyOut,
    AssuranceDutyUpdate,
    AssuranceOut,
    AssuranceProgress,
    AssuranceSummary,
    AssuranceSummaryIssue,
    AssuranceUpdate,
)
from app.schemas.common import NameValue
from app.schemas.restroom import RestroomBrief

SORTABLE_FIELDS = {
    "start_date": Assurance.start_date,
    "end_date": Assurance.end_date,
    "created_at": Assurance.created_at,
    "updated_at": Assurance.updated_at,
    "level": Assurance.level,
    "code": Assurance.code,
}

# 保障中允许修改的非结构性字段
ACTIVE_EDITABLE_FIELDS = {"name", "requirements", "contact", "remark"}
# 出现即需要重新展开重点对象与值守安排的结构性字段
STRUCTURAL_FIELDS = {
    "start_date",
    "end_date",
    "level",
    "daily_count",
    "districts",
    "restroom_ids",
}
# 终态状态
CLOSED_STATUSES = {AssuranceStatus.FINISHED.value, AssuranceStatus.CANCELLED.value}


def _next_code(db: Session, day: date) -> str:
    """生成形如 BZ-20260918-001 的保障编号。"""
    prefix = f"BZ-{day.strftime('%Y%m%d')}"
    seq = (
        db.scalar(select(func.count()).select_from(Assurance).where(Assurance.code.like(f"{prefix}-%")))
        or 0
    ) + 1
    while True:
        code = f"{prefix}-{seq:03d}"
        if not db.scalar(select(Assurance.id).where(Assurance.code == code)):
            return code
        seq += 1


def _enum(value):
    return value.value if hasattr(value, "value") else value


def get_assurance(db: Session, assurance_id: int) -> Assurance:
    assurance = db.get(Assurance, assurance_id)
    if assurance is None:
        raise NotFoundError(f"保障 {assurance_id} 不存在")
    return assurance


# --------------------------------------------------------------------------- #
# 重点对象与值守排班
# --------------------------------------------------------------------------- #

def _expand_targets(
    db: Session, districts: list[str], restroom_ids: list[int]
) -> list[tuple[Restroom, str]]:
    """重点区域内正常开放公厕 ∪ 额外指定公厕，按公厕去重。"""
    chosen: dict[int, tuple[Restroom, str]] = {}
    if districts:
        rows = db.scalars(
            select(Restroom).where(
                Restroom.district.in_(districts),
                Restroom.status == RestroomStatus.NORMAL.value,
            )
        )
        for room in rows:
            chosen[room.id] = (room, TARGET_SOURCE_DISTRICT)
    if restroom_ids:
        rooms = list(db.scalars(select(Restroom).where(Restroom.id.in_(restroom_ids))))
        found = {room.id for room in rooms}
        missing = [rid for rid in dict.fromkeys(restroom_ids) if rid not in found]
        if missing:
            raise DomainError(f"公厕 {', '.join(map(str, missing))} 不存在")
        for room in rooms:
            chosen.setdefault(room.id, (room, TARGET_SOURCE_MANUAL))
    if not chosen:
        raise DomainError("至少选择一个能展开出公厕的重点区域或重点公厕")
    return [chosen[rid] for rid in sorted(chosen)]


def _personnel_pool(db: Session, restroom_ids: list[int]) -> list[str]:
    """值守人候选池：优先近期巡查的巡查员（按最近巡查时间倒序），不足时补充公厕责任人。"""
    pool: list[str] = []
    rows = db.execute(
        select(Inspection.inspector, func.max(Inspection.inspect_time))
        .where(Inspection.restroom_id.in_(restroom_ids), Inspection.inspector != "")
        .group_by(Inspection.inspector)
        .order_by(func.max(Inspection.inspect_time).desc())
    ).all()
    for inspector, _ in rows:
        if inspector and inspector not in pool:
            pool.append(inspector)
    managers = db.scalars(
        select(Restroom.manager)
        .where(Restroom.id.in_(restroom_ids), Restroom.manager != "")
        .order_by(Restroom.id)
    )
    for manager in managers:
        if manager and manager not in pool:
            pool.append(manager)
    return pool


def resolve_shift_plan(level: str, daily: int | None) -> tuple[int, dict[str, int]]:
    """按等级带出预置频次，并用手动 daily 微调，保证各班次之和等于 daily 且每班至少 1 次。"""
    template = ASSURANCE_SHIFT_PLAN[level]
    plan = {shift: int(count) for shift, count in template["by_shift"].items()}
    if daily is None:
        return int(template["daily"]), plan
    if daily < ASSURANCE_DAILY_MIN:
        raise DomainError(f"每日巡查次数不能少于 {ASSURANCE_DAILY_MIN} 次")
    delta = daily - int(template["daily"])
    if delta > 0:
        plan[ASSURANCE_SHIFT_ORDER[0]] += delta
    elif delta < 0:
        remaining = -delta
        for shift in reversed(ASSURANCE_SHIFT_ORDER):
            take = min(remaining, plan[shift] - 1)
            plan[shift] -= take
            remaining -= take
            if remaining == 0:
                break
        if remaining > 0:
            raise DomainError("每日巡查次数过低，无法保证每个班次至少巡查 1 次")
    return daily, plan


def _build_duties(
    assurance: Assurance,
    targets: list[AssuranceTarget],
    shift_plan: dict[str, int],
    pool: list[str],
) -> list[AssuranceDuty]:
    """生成 天 × 班次 × 重点公厕 的值守岗位，并在候选人间全局轮排。"""
    days = (assurance.end_date - assurance.start_date).days + 1
    duties: list[AssuranceDuty] = []
    cursor = 0
    for offset in range(days):
        duty_day = assurance.start_date + timedelta(days=offset)
        for shift in ASSURANCE_SHIFT_ORDER:
            planned = int(shift_plan.get(shift, 1))
            for target in targets:
                assignee = pool[cursor % len(pool)] if pool else ""
                if pool:
                    cursor += 1
                duties.append(
                    AssuranceDuty(
                        restroom_id=target.restroom_id,
                        duty_date=duty_day,
                        shift=shift,
                        planned_count=planned,
                        assignee=assignee,
                    )
                )
    return duties


def _persist_targets(db: Session, assurance: Assurance, rooms: list[tuple[Restroom, str]]):
    targets: list[AssuranceTarget] = []
    for room, source in rooms:
        target = AssuranceTarget(
            assurance_id=assurance.id,
            restroom_id=room.id,
            source=source,
            district=room.district or "",
        )
        db.add(target)
        targets.append(target)
    return targets


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #

def create_assurance(db: Session, payload: AssuranceCreate) -> Assurance:
    level = _enum(payload.level)
    start_date, end_date = payload.start_date, payload.end_date
    daily, shift_plan = resolve_shift_plan(level, payload.daily_count)
    rooms = _expand_targets(db, payload.districts, payload.restroom_ids)

    assurance = Assurance(
        code=_next_code(db, start_date),
        name=payload.name,
        assurance_type=_enum(payload.assurance_type),
        level=level,
        status=AssuranceStatus.PREPARING.value,
        start_date=start_date,
        end_date=end_date,
        daily_count=daily,
        shift_plan=shift_plan,
        requirements=list(payload.requirements),
        contact=payload.contact,
        remark=payload.remark,
        action_log=[
            {
                "action": "创建保障",
                "operator": payload.contact or "系统",
                "remark": f"按「{level}」自动加密，重点公厕 {len(rooms)} 座",
                "at": datetime.now().isoformat(timespec="seconds"),
            }
        ],
    )
    db.add(assurance)
    db.flush()
    targets = _persist_targets(db, assurance, rooms)
    pool = _personnel_pool(db, [room.id for room, _ in rooms])
    for duty in _build_duties(assurance, targets, shift_plan, pool):
        duty.assurance_id = assurance.id
        db.add(duty)
    db.commit()
    return get_assurance(db, assurance.id)


def _rebuild_structure(db: Session, assurance: Assurance, data: dict) -> None:
    """结构性字段变更：重新展开重点对象并重排值守，保留原岗位上的手工改派。"""
    start_date = data.get("start_date", assurance.start_date)
    end_date = data.get("end_date", assurance.end_date)
    if end_date < start_date:
        raise DomainError("保障结束日期不能早于开始日期")
    level = _enum(data.get("level", assurance.level))
    if "daily_count" in data:
        daily_value = data["daily_count"]
    elif "level" in data:
        # 切换等级且未显式指定次数时，采用新等级的预置频次
        daily_value = None
    else:
        daily_value = assurance.daily_count
    daily, shift_plan = resolve_shift_plan(level, daily_value)
    districts = data["districts"] if data.get("districts") is not None else None
    restroom_ids = data["restroom_ids"] if data.get("restroom_ids") is not None else None
    if districts is None and restroom_ids is None:
        # 仅时段/等级/频次变化：沿用既有重点对象
        rooms = [(target.restroom, target.source) for target in assurance.targets]
    else:
        effective_districts = districts if districts is not None else sorted(
            {target.district for target in assurance.targets if target.source == TARGET_SOURCE_DISTRICT}
        )
        effective_manual = (
            restroom_ids
            if restroom_ids is not None
            else [t.restroom_id for t in assurance.targets if t.source == TARGET_SOURCE_MANUAL]
        )
        rooms = _expand_targets(db, effective_districts, effective_manual)

    # 记录旧岗位的手工改派，重建后按 (日期, 班次, 公厕) 回贴
    overrides: dict[tuple[date, str, int], tuple[str, str | None]] = {
        (duty.duty_date, duty.shift, duty.restroom_id): (duty.assignee, duty.remark)
        for duty in assurance.duties
    }

    assurance.start_date = start_date
    assurance.end_date = end_date
    assurance.level = level
    assurance.daily_count = daily
    assurance.shift_plan = shift_plan

    for duty in assurance.duties:
        db.delete(duty)
    for target in list(assurance.targets):
        db.delete(target)
    db.flush()

    targets = _persist_targets(db, assurance, rooms)
    pool = _personnel_pool(db, [room.id for room, _ in rooms])
    for duty in _build_duties(assurance, targets, shift_plan, pool):
        duty.assurance_id = assurance.id
        kept = overrides.get((duty.duty_date, duty.shift, duty.restroom_id))
        if kept:
            duty.assignee, duty.remark = kept
        db.add(duty)


def update_assurance(db: Session, assurance_id: int, payload: AssuranceUpdate) -> Assurance:
    assurance = get_assurance(db, assurance_id)
    if assurance.status in CLOSED_STATUSES:
        raise DomainError(f"保障已「{assurance.status}」，不能再修改")

    data = payload.model_dump(exclude_unset=True)
    if assurance.status == AssuranceStatus.ACTIVE.value:
        forbidden = [key for key in data if key not in ACTIVE_EDITABLE_FIELDS]
        if forbidden:
            raise DomainError("保障进行中仅可修改保障名称、保障要求、联络人与备注；值守调整请到值守安排中改派")

    structural = {key: value for key, value in data.items() if key in STRUCTURAL_FIELDS}
    for key, value in data.items():
        if key in STRUCTURAL_FIELDS:
            continue
        setattr(assurance, key, _enum(value))

    if structural:
        _rebuild_structure(db, assurance, structural)

    db.commit()
    return get_assurance(db, assurance_id)


def change_status(
    db: Session, assurance_id: int, target: AssuranceStatus, payload: AssuranceAction
) -> Assurance:
    assurance = get_assurance(db, assurance_id)
    target_value = target.value if hasattr(target, "value") else target
    if target_value == assurance.status:
        raise DomainError(f"保障已处于「{target_value}」状态")
    allowed = ASSURANCE_TRANSITIONS.get(assurance.status, [])
    if target_value not in allowed:
        raise DomainError(
            f"当前状态「{assurance.status}」不允许变更为「{target_value}」，可选："
            + ("、".join(allowed) if allowed else "无（流程已结束）")
        )

    now = datetime.now()
    from_status = assurance.status

    # 结束前先归集问题并固化小结（此时仍为保障中，自动归属规则可以命中本保障）
    if target_value == AssuranceStatus.FINISHED.value:
        relink_issues(db, assurance_id, commit=False)
        build_summary(db, assurance, persist=True)

    assurance.status = target_value
    if target_value == AssuranceStatus.ACTIVE.value:
        assurance.started_at = now
    elif target_value == AssuranceStatus.FINISHED.value:
        assurance.finished_at = now
    elif target_value == AssuranceStatus.CANCELLED.value:
        assurance.cancelled_at = now

    log = list(assurance.action_log or [])
    log.append(
        {
            "action": ASSURANCE_TRANSITION_ACTIONS.get((from_status, target_value), "状态变更"),
            "operator": payload.operator,
            "remark": payload.remark,
            "at": now.isoformat(timespec="seconds"),
        }
    )
    assurance.action_log = log

    db.commit()
    return get_assurance(db, assurance_id)


def delete_assurance(db: Session, assurance_id: int, *, force: bool = False) -> None:
    assurance = get_assurance(db, assurance_id)
    linked = db.scalar(
        select(func.count()).select_from(Issue).where(Issue.assurance_id == assurance_id)
    ) or 0
    if linked and not force:
        raise ConflictError(
            f"该保障已归集 {linked} 条问题，确需删除请使用 force=true，问题将解除保障归属"
        )
    if assurance.status == AssuranceStatus.ACTIVE.value:
        raise ConflictError("保障进行中，不能删除；如需终止请先取消或结束保障")
    if linked:
        for issue in db.scalars(select(Issue).where(Issue.assurance_id == assurance_id)):
            issue.assurance_id = None
    db.delete(assurance)
    db.commit()


def detach_restroom(db: Session, restroom_id: int) -> None:
    """公厕被强删时，显式清理其保障重点对象与值守岗位（兼容 SQLite 外键不生效的情况）。"""
    for duty in db.scalars(
        select(AssuranceDuty).where(AssuranceDuty.restroom_id == restroom_id)
    ):
        db.delete(duty)
    for target in db.scalars(
        select(AssuranceTarget).where(AssuranceTarget.restroom_id == restroom_id)
    ):
        db.delete(target)
    db.flush()


# --------------------------------------------------------------------------- #
# 查询与进度统计
# --------------------------------------------------------------------------- #

def list_assurances(
    db: Session,
    *,
    status: str | None = None,
    level: str | None = None,
    assurance_type: str | None = None,
    keyword: str | None = None,
    active_on: date | None = None,
    page: int = 1,
    page_size: int = 10,
    sort_by: str = "start_date",
    order: str = "desc",
) -> tuple[list[Assurance], int]:
    stmt = select(Assurance)
    if status:
        stmt = stmt.where(Assurance.status == status)
    if level:
        stmt = stmt.where(Assurance.level == level)
    if assurance_type:
        stmt = stmt.where(Assurance.assurance_type == assurance_type)
    if active_on:
        stmt = stmt.where(
            Assurance.start_date <= active_on, Assurance.end_date >= active_on
        )
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(Assurance.name.like(like), Assurance.code.like(like), Assurance.contact.like(like))
        )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = SORTABLE_FIELDS.get(sort_by, Assurance.start_date)
    stmt = stmt.order_by(column.desc() if order == "desc" else column.asc(), Assurance.id.desc())
    rows = list(db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)))
    return rows, total


def _target_restroom_ids(assurance: Assurance) -> list[int]:
    return sorted({target.restroom_id for target in assurance.targets})


def _inspection_stats(
    db: Session, assurance: Assurance
) -> tuple[dict[tuple[int, date, str], int], dict[tuple[int, date], list[float]]]:
    """一次性拉取保障时段内重点公厕的巡查，在内存按 (公厕, 日期, 班次) 分桶，避免 N+1。"""
    ids = _target_restroom_ids(assurance)
    counts: dict[tuple[int, date, str], int] = {}
    scores: dict[tuple[int, date], list[float]] = {}
    if not ids:
        return counts, scores
    rows = db.execute(
        select(Inspection.restroom_id, Inspection.inspect_time, Inspection.shift, Inspection.score).where(
            Inspection.restroom_id.in_(ids),
            Inspection.inspect_time >= datetime.combine(assurance.start_date, time.min),
            Inspection.inspect_time <= datetime.combine(assurance.end_date, time.max),
        )
    ).all()
    for restroom_id, inspect_time, shift, score in rows:
        day = inspect_time.date()
        key = (restroom_id, day, shift)
        counts[key] = counts.get(key, 0) + 1
        scores.setdefault((restroom_id, day), []).append(float(score or 0))
    return counts, scores


def _as_of(assurance: Assurance) -> date:
    today = datetime.now().date()
    if today < assurance.start_date:
        return assurance.start_date
    return min(today, assurance.end_date)


def build_progress(db: Session, assurance: Assurance) -> AssuranceProgress:
    counts, _ = _inspection_stats(db, assurance)
    as_of = _as_of(assurance)
    due = [duty for duty in assurance.duties if duty.duty_date <= as_of]
    completed = 0
    planned_total = 0
    actual_total = 0
    for duty in due:
        actual = counts.get((duty.restroom_id, duty.duty_date, duty.shift), 0)
        planned_total += duty.planned_count
        actual_total += min(actual, duty.planned_count)
        if actual >= duty.planned_count:
            completed += 1
    due_count = len(due)
    return AssuranceProgress(
        as_of=as_of,
        total_days=(assurance.end_date - assurance.start_date).days + 1,
        target_count=len(assurance.targets),
        due_duty_count=due_count,
        completed_duty_count=completed,
        duty_completion_rate=round(completed / due_count * 100, 1) if due_count else 0.0,
        planned_inspection_count=planned_total,
        actual_inspection_count=actual_total,
        inspection_completion_rate=round(actual_total / planned_total * 100, 1)
        if planned_total
        else 0.0,
    )


def _duty_to_out(duty: AssuranceDuty, counts: dict) -> AssuranceDutyOut:
    actual = counts.get((duty.restroom_id, duty.duty_date, duty.shift), 0)
    return AssuranceDutyOut(
        id=duty.id,
        restroom_id=duty.restroom_id,
        restroom=RestroomBrief.model_validate(duty.restroom) if duty.restroom is not None else None,
        duty_date=duty.duty_date,
        shift=duty.shift,
        planned_count=duty.planned_count,
        actual_count=actual,
        completed=actual >= duty.planned_count,
        assignee=duty.assignee,
        remark=duty.remark,
    )


def list_duties(
    db: Session,
    assurance_id: int,
    *,
    duty_date: date | None = None,
    shift: str | None = None,
    restroom_id: int | None = None,
    assignee: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[AssuranceDuty], int]:
    assurance = get_assurance(db, assurance_id)
    counts, _ = _inspection_stats(db, assurance)
    stmt = select(AssuranceDuty).where(AssuranceDuty.assurance_id == assurance_id)
    if duty_date:
        stmt = stmt.where(AssuranceDuty.duty_date == duty_date)
    if shift:
        stmt = stmt.where(AssuranceDuty.shift == shift)
    if restroom_id:
        stmt = stmt.where(AssuranceDuty.restroom_id == restroom_id)
    if assignee:
        stmt = stmt.where(AssuranceDuty.assignee.like(f"%{assignee.strip()}%"))
    stmt = stmt.order_by(
        AssuranceDuty.duty_date.asc(),
        AssuranceDuty.shift.asc(),
        AssuranceDuty.restroom_id.asc(),
        AssuranceDuty.id.asc(),
    )
    rows = list(db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)))
    total = db.scalar(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ) or 0
    return rows, total, counts


def update_duty(
    db: Session, assurance_id: int, duty_id: int, payload: AssuranceDutyUpdate
) -> AssuranceDuty:
    assurance = get_assurance(db, assurance_id)
    if assurance.status in CLOSED_STATUSES:
        raise DomainError(f"保障已「{assurance.status}」，值守岗位不能再改派")
    duty = db.get(AssuranceDuty, duty_id)
    if duty is None or duty.assurance_id != assurance_id:
        raise NotFoundError(f"值守岗位 {duty_id} 不存在")
    data = payload.model_dump(exclude_unset=True)
    if "assignee" in data:
        duty.assignee = (data["assignee"] or "").strip()
    if "remark" in data:
        duty.remark = data["remark"]
    db.commit()
    db.refresh(duty)
    return duty


def regenerate_duties(db: Session, assurance_id: int) -> Assurance:
    assurance = get_assurance(db, assurance_id)
    if assurance.status != AssuranceStatus.PREPARING.value:
        raise DomainError("仅筹备中的保障可以重新自动排班")
    rooms = [(target.restroom, target.source) for target in assurance.targets]
    overrides = {
        (duty.duty_date, duty.shift, duty.restroom_id): (duty.assignee, duty.remark)
        for duty in assurance.duties
    }
    for duty in assurance.duties:
        db.delete(duty)
    for target in list(assurance.targets):
        db.delete(target)
    db.flush()
    targets = _persist_targets(db, assurance, rooms)
    pool = _personnel_pool(db, [room.id for room, _ in rooms])
    for duty in _build_duties(assurance, targets, assurance.shift_plan, pool):
        duty.assurance_id = assurance.id
        kept = overrides.get((duty.duty_date, duty.shift, duty.restroom_id))
        if kept:
            duty.assignee, duty.remark = kept
        db.add(duty)
    db.commit()
    return get_assurance(db, assurance_id)


# --------------------------------------------------------------------------- #
# 问题自动归属
# --------------------------------------------------------------------------- #

def match_assurance(db: Session, restroom_id: int, when: datetime) -> Assurance | None:
    """问题自动归属：公厕为重点对象、上报时间在保障时段内；多保障命中时取最高等级、再取最近开始。"""
    day = when.date() if isinstance(when, datetime) else when
    rows = list(
        db.scalars(
            select(Assurance)
            .join(AssuranceTarget, AssuranceTarget.assurance_id == Assurance.id)
            .where(
                AssuranceTarget.restroom_id == restroom_id,
                Assurance.status.in_(ASSURANCE_ACTIVE_STATUSES),
                Assurance.start_date <= day,
                Assurance.end_date >= day,
            )
        )
    )
    if not rows:
        return None
    rows.sort(key=lambda item: (ASSURANCE_LEVEL_RANK.get(item.level, 99), -item.start_date.toordinal()))
    return rows[0]


def assert_target(assurance: Assurance, restroom_id: int) -> None:
    if not any(target.restroom_id == restroom_id for target in assurance.targets):
        raise DomainError(f"公厕不属于保障「{assurance.name}」的重点对象")


def relink_issues(db: Session, assurance_id: int, *, commit: bool = True) -> int:
    """把保障时段内、重点公厕上尚未归属保障的问题归集进来（重叠时不抢占更高等级保障）。"""
    assurance = get_assurance(db, assurance_id)
    ids = _target_restroom_ids(assurance)
    if not ids:
        return 0
    pending = list(
        db.scalars(
            select(Issue).where(
                Issue.assurance_id.is_(None),
                Issue.restroom_id.in_(ids),
                Issue.report_time >= datetime.combine(assurance.start_date, time.min),
                Issue.report_time <= datetime.combine(assurance.end_date, time.max),
            )
        )
    )
    count = 0
    for issue in pending:
        winner = match_assurance(db, issue.restroom_id, issue.report_time)
        if winner is not None and winner.id == assurance_id:
            issue.assurance_id = assurance_id
            count += 1
    if commit:
        db.commit()
    return count


# --------------------------------------------------------------------------- #
# 保障情况小结
# --------------------------------------------------------------------------- #

def _issue_overdue(issue: Issue) -> bool:
    return (
        issue.deadline is not None
        and issue.status in OPEN_ISSUE_STATUSES
        and issue.deadline < datetime.now()
    )


def build_summary(db: Session, assurance: Assurance, *, persist: bool = False) -> AssuranceSummary:
    progress = build_progress(db, assurance)
    _, score_buckets = _inspection_stats(db, assurance)
    all_scores = [score for values in score_buckets.values() for score in values]

    issues = list(
        db.scalars(select(Issue).where(Issue.assurance_id == assurance.id))
    )
    open_issues = [item for item in issues if item.status in OPEN_ISSUE_STATUSES]
    closed_issues = [
        item for item in issues if item.status in (IssueStatus.DONE.value, IssueStatus.CLOSED.value)
    ]
    overdue = [item for item in open_issues if _issue_overdue(item)]

    def distribution(getter, order) -> list[NameValue]:
        counter: dict[str, int] = {}
        for item in issues:
            counter[getter(item)] = counter.get(getter(item), 0) + 1
        return [NameValue(name=name, value=float(counter.get(name, 0))) for name in order]

    districts = sorted({target.district for target in assurance.targets if target.district})
    restroom_names = {target.restroom_id: target.restroom.name for target in assurance.targets}
    open_items = [
        AssuranceSummaryIssue(
            id=item.id,
            code=item.code,
            title=item.title,
            restroom_name=restroom_names.get(item.restroom_id, ""),
            district=next(
                (t.district for t in assurance.targets if t.restroom_id == item.restroom_id), ""
            ),
            category=item.category,
            severity=item.severity,
            status=item.status,
            deadline=item.deadline,
        )
        for item in sorted(open_issues, key=lambda x: x.report_time, reverse=True)[:50]
    ]

    duty_planned = len(assurance.duties)
    duty_due = progress.due_duty_count
    duty_completed = progress.completed_duty_count
    summary = AssuranceSummary(
        generated_at=datetime.now(),
        name=assurance.name,
        code=assurance.code,
        assurance_type=assurance.assurance_type,
        level=assurance.level,
        start_date=assurance.start_date,
        end_date=assurance.end_date,
        days=progress.total_days,
        districts=districts,
        district_count=len(districts),
        target_count=progress.target_count,
        duty_planned=duty_planned,
        duty_due=duty_due,
        duty_completed=duty_completed,
        duty_completion_rate=round(duty_completed / duty_due * 100, 1) if duty_due else 0.0,
        inspection_planned=progress.planned_inspection_count,
        inspection_actual=progress.actual_inspection_count,
        inspection_completion_rate=progress.inspection_completion_rate,
        avg_score=round(sum(all_scores) / len(all_scores), 1) if all_scores else None,
        issue_total=len(issues),
        issue_open=len(open_issues),
        issue_closed=len(closed_issues),
        issue_overdue=len(overdue),
        issue_by_category=distribution(lambda i: i.category, [c.value for c in IssueCategory]),
        issue_by_severity=distribution(lambda i: i.severity, [s.value for s in IssueSeverity]),
        issue_by_district=[
            NameValue(name=name, value=float(sum(1 for i in issues if next(
                (t.district for t in assurance.targets if t.restroom_id == i.restroom_id), ""
            ) == name)))
            for name in districts
        ],
        open_items=open_items,
    )

    if persist:
        assurance.summary = summary.model_dump(mode="json")
        assurance.summary_generated_at = datetime.now()
        db.flush()
    return summary


def refresh_summary(db: Session, assurance_id: int) -> Assurance:
    assurance = get_assurance(db, assurance_id)
    build_summary(db, assurance, persist=True)
    db.commit()
    return get_assurance(db, assurance_id)


# --------------------------------------------------------------------------- #
# 输出装配
# --------------------------------------------------------------------------- #

def to_out(assurance: Assurance) -> AssuranceOut:
    return AssuranceOut(
        id=assurance.id,
        code=assurance.code,
        name=assurance.name,
        assurance_type=assurance.assurance_type,
        level=assurance.level,
        status=assurance.status,
        start_date=assurance.start_date,
        end_date=assurance.end_date,
        daily_count=assurance.daily_count,
        shift_plan=dict(assurance.shift_plan or {}),
        requirements=list(assurance.requirements or []),
        contact=assurance.contact,
        remark=assurance.remark,
        started_at=assurance.started_at,
        finished_at=assurance.finished_at,
        cancelled_at=assurance.cancelled_at,
        created_at=assurance.created_at,
        updated_at=assurance.updated_at,
        target_count=len(assurance.targets),
        district_count=len({t.district for t in assurance.targets if t.district}),
    )


def _issue_counts(db: Session, assurance_id: int) -> tuple[int, int]:
    total = db.scalar(
        select(func.count()).select_from(Issue).where(Issue.assurance_id == assurance_id)
    ) or 0
    open_count = db.scalar(
        select(func.count())
        .select_from(Issue)
        .where(Issue.assurance_id == assurance_id, Issue.status.in_(OPEN_ISSUE_STATUSES))
    ) or 0
    return total, open_count


def to_detail(db: Session, assurance: Assurance) -> AssuranceDetail:
    from app.schemas.assurance import AssuranceTargetOut

    base = to_out(assurance).model_dump()
    issue_total, issue_open = _issue_counts(db, assurance.id)
    summary = None
    if assurance.summary:
        summary = AssuranceSummary.model_validate(assurance.summary)
    return AssuranceDetail(
        **base,
        targets=[
            AssuranceTargetOut(
                id=target.id,
                restroom_id=target.restroom_id,
                source=target.source,
                district=target.district,
                restroom=RestroomBrief.model_validate(target.restroom)
                if target.restroom is not None
                else None,
            )
            for target in sorted(assurance.targets, key=lambda t: t.id)
        ],
        progress=build_progress(db, assurance),
        issue_total=issue_total,
        issue_open=issue_open,
        summary=summary,
        summary_generated_at=assurance.summary_generated_at,
        action_log=list(assurance.action_log or []),
    )


def duty_page_to_out(rows: list[AssuranceDuty], counts: dict) -> list[AssuranceDutyOut]:
    return [_duty_to_out(duty, counts) for duty in rows]


def get_duty_out(db: Session, assurance: Assurance, duty: AssuranceDuty) -> AssuranceDutyOut:
    counts, _ = _inspection_stats(db, assurance)
    return _duty_to_out(duty, counts)


def active_assurances(db: Session):
    """首页横幅：保障中，以及 7 天内即将开始的筹备中保障。"""
    from app.schemas.stats import ActiveAssuranceBrief

    today = datetime.now().date()
    rows = list(
        db.scalars(
            select(Assurance)
            .where(
                or_(
                    Assurance.status == AssuranceStatus.ACTIVE.value,
                    (
                        (Assurance.status == AssuranceStatus.PREPARING.value)
                        & (Assurance.start_date <= today + timedelta(days=7))
                    ),
                )
            )
            .order_by(Assurance.start_date.asc())
        )
    )
    result = []
    for assurance in rows:
        progress = build_progress(db, assurance)
        _, open_count = _issue_counts(db, assurance.id)
        result.append(
            ActiveAssuranceBrief(
                id=assurance.id,
                code=assurance.code,
                name=assurance.name,
                level=assurance.level,
                status=assurance.status,
                start_date=assurance.start_date,
                end_date=assurance.end_date,
                target_count=len(assurance.targets),
                duty_completion_rate=progress.duty_completion_rate,
                issue_open=open_count,
            )
        )
    return result
