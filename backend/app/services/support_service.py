"""节假日与重大活动保障业务逻辑。"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import (
    OPEN_ISSUE_STATUSES,
    SUPPORT_LEVEL_RULES,
    SUPPORT_PLAN_TRANSITIONS,
    IssueCategory,
    IssueSeverity,
    IssueStatus,
    SupportStatus,
)
from app.core.exceptions import DomainError, NotFoundError
from app.models import Inspection, Issue, Restroom, SupportDuty, SupportPlan
from app.schemas.issue import IssueOut
from app.schemas.restroom import RestroomBrief
from app.schemas.stats import NameValue
from app.schemas.support import (
    SupportDutyOut,
    SupportPlanCreate,
    SupportPlanDetail,
    SupportPlanOut,
    SupportPlanUpdate,
    SupportSummary,
)
from app.services import issue_service

SORTABLE_FIELDS = {
    "start_date": SupportPlan.start_date,
    "end_date": SupportPlan.end_date,
    "created_at": SupportPlan.created_at,
    "level": SupportPlan.level,
}


def _next_code(db: Session) -> str:
    """生成形如 BZ-20260918-001 的保障编号。"""
    prefix = datetime.now().strftime("BZ-%Y%m%d")
    seq = (
        db.scalar(
            select(func.count()).select_from(SupportPlan).where(SupportPlan.code.like(f"{prefix}-%"))
        )
        or 0
    ) + 1
    while True:
        code = f"{prefix}-{seq:03d}"
        if not db.scalar(select(SupportPlan.id).where(SupportPlan.code == code)):
            return code
        seq += 1


def _level_shifts(level: str) -> list[str]:
    rule = SUPPORT_LEVEL_RULES.get(level) or {}
    return list(rule.get("shifts", []))


def _default_inspections_per_day(level: str) -> int:
    rule = SUPPORT_LEVEL_RULES.get(level) or {}
    return int(rule.get("inspections_per_day", 1))


def get_plan(db: Session, plan_id: int) -> SupportPlan:
    plan = db.get(SupportPlan, plan_id)
    if plan is None:
        raise NotFoundError(f"保障方案 {plan_id} 不存在")
    return plan


def key_restrooms(db: Session, plan: SupportPlan) -> list[Restroom]:
    """解析保障范围：重点区域内的公厕 ∪ 额外指定的重点公厕。"""
    stmt = select(Restroom).order_by(Restroom.code)
    conditions = []
    if plan.districts:
        conditions.append(Restroom.district.in_(plan.districts))
    if plan.restroom_ids:
        conditions.append(Restroom.id.in_(plan.restroom_ids))
    if not conditions:
        return []
    stmt = stmt.where(or_(*conditions))
    return list(db.scalars(stmt))


def to_out(db: Session, plan: SupportPlan) -> SupportPlanOut:
    data = SupportPlanOut.model_validate(plan)
    data.duty_count = len(plan.duties)
    data.key_restroom_count = len(key_restrooms(db, plan))
    return data


def to_detail(db: Session, plan: SupportPlan) -> SupportPlanDetail:
    base = to_out(db, plan).model_dump()
    restrooms = key_restrooms(db, plan)
    return SupportPlanDetail(
        **base,
        duties=[SupportDutyOut.model_validate(duty) for duty in plan.duties],
        key_restrooms=[RestroomBrief.model_validate(room) for room in restrooms],
    )


def list_plans(
    db: Session,
    *,
    keyword: str | None = None,
    category: str | None = None,
    level: str | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 10,
    sort_by: str = "created_at",
    order: str = "desc",
) -> tuple[list[SupportPlan], int]:
    stmt = select(SupportPlan)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(
                SupportPlan.name.like(like),
                SupportPlan.code.like(like),
                SupportPlan.requirements.like(like),
            )
        )
    if category:
        stmt = stmt.where(SupportPlan.category == category)
    if level:
        stmt = stmt.where(SupportPlan.level == level)
    if status:
        stmt = stmt.where(SupportPlan.status == status)
    if date_from:
        stmt = stmt.where(SupportPlan.end_date >= date_from)
    if date_to:
        stmt = stmt.where(SupportPlan.start_date <= date_to)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = SORTABLE_FIELDS.get(sort_by, SupportPlan.created_at)
    stmt = stmt.order_by(column.desc() if order == "desc" else column.asc(), SupportPlan.id.desc())
    rows = list(db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)))
    return rows, total


def _normalize_staff(staff_pool: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for name in staff_pool:
        name = str(name).strip()
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result


def create_plan(db: Session, payload: SupportPlanCreate) -> SupportPlan:
    data = payload.model_dump(exclude={"code"})
    data = {key: (value.value if hasattr(value, "value") else value) for key, value in data.items()}
    code = (payload.code or "").strip() or _next_code(db)
    if db.scalar(select(SupportPlan.id).where(SupportPlan.code == code)):
        raise DomainError(f"保障编号 {code} 已存在")
    if data.get("inspections_per_day") is None:
        data["inspections_per_day"] = _default_inspections_per_day(data["level"])
    data["staff_pool"] = _normalize_staff(data.get("staff_pool") or [])
    plan = SupportPlan(code=code, status=SupportStatus.PREPARING.value, **data)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def update_plan(db: Session, plan_id: int, payload: SupportPlanUpdate) -> SupportPlan:
    plan = get_plan(db, plan_id)
    data = payload.model_dump(exclude_unset=True)
    start = data.get("start_date", plan.start_date)
    end = data.get("end_date", plan.end_date)
    if end < start:
        raise DomainError("保障结束日期不能早于开始日期")
    level_changed = data.get("level") is not None and data["level"] != plan.level
    for key, value in data.items():
        value = value.value if hasattr(value, "value") else value
        if key == "staff_pool" and value is not None:
            value = _normalize_staff(value)
        setattr(plan, key, value)
    # 等级调整且未显式指定频次时，按新等级重新带出默认频次
    if level_changed and data.get("inspections_per_day") is None:
        plan.inspections_per_day = _default_inspections_per_day(plan.level)
    db.commit()
    db.refresh(plan)
    return plan


def delete_plan(db: Session, plan_id: int) -> None:
    plan = get_plan(db, plan_id)
    db.delete(plan)
    db.commit()


def generate_duties(db: Session, plan: SupportPlan) -> list[SupportDuty]:
    """按保障时段与等级班次重新生成值守安排，值守人员按名单轮值。"""
    shifts = _level_shifts(plan.level)
    if not shifts:
        raise DomainError(f"保障等级「{plan.level}」未配置值守班次")

    staff = list(plan.staff_pool)
    if not staff:
        # 名单为空时默认取重点公厕的保洁责任人
        staff = _normalize_staff([room.manager for room in key_restrooms(db, plan)])
    if not staff:
        raise DomainError("值守人员名单为空，请先维护值守人员或重点公厕")

    phones = {room.manager: room.manager_phone for room in key_restrooms(db, plan)}

    plan.duties.clear()
    db.flush()

    days = (plan.end_date - plan.start_date).days
    cursor = 0
    for offset in range(days + 1):
        duty_date = plan.start_date + timedelta(days=offset)
        for shift in shifts:
            name = staff[cursor % len(staff)]
            cursor += 1
            plan.duties.append(
                SupportDuty(
                    duty_date=duty_date,
                    shift=shift,
                    staff=name,
                    phone=phones.get(name, ""),
                )
            )
    db.commit()
    db.refresh(plan)
    return plan.duties


def activate_plan(db: Session, plan_id: int) -> SupportPlan:
    """启动保障：进入进行中状态，并按等级自动生成加密巡查所需的值守安排。"""
    plan = get_plan(db, plan_id)
    if SupportStatus.ACTIVE.value not in SUPPORT_PLAN_TRANSITIONS.get(plan.status, []):
        raise DomainError(f"当前状态「{plan.status}」不允许启动保障")
    plan.status = SupportStatus.ACTIVE.value
    db.commit()
    db.refresh(plan)
    if not plan.duties:
        generate_duties(db, plan)
    return plan


def finish_plan(db: Session, plan_id: int) -> SupportPlan:
    """结束保障：进入已结束状态，并自动生成保障情况小结草稿。"""
    plan = get_plan(db, plan_id)
    if SupportStatus.FINISHED.value not in SUPPORT_PLAN_TRANSITIONS.get(plan.status, []):
        raise DomainError(f"当前状态「{plan.status}」不允许结束保障")
    plan.status = SupportStatus.FINISHED.value
    if not plan.conclusion:
        plan.conclusion = build_summary(db, plan).summary_text
    db.commit()
    db.refresh(plan)
    return plan


def _period_bounds(plan: SupportPlan) -> tuple[datetime, datetime]:
    return (
        datetime.combine(plan.start_date, time.min),
        datetime.combine(plan.end_date, time.max),
    )


def plan_issues(
    db: Session,
    plan: SupportPlan,
    *,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[Issue], int]:
    """保障期间、保障范围内公厕的问题，单独汇总。"""
    restroom_ids = [room.id for room in key_restrooms(db, plan)]
    if not restroom_ids:
        return [], 0
    return issue_service.list_issues(
        db,
        restroom_ids=restroom_ids,
        date_from=plan.start_date,
        date_to=plan.end_date,
        page=page,
        page_size=page_size,
        sort_by="report_time",
    )


def _build_summary_text(
    plan: SupportPlan,
    *,
    days: int,
    key_count: int,
    duty_total: int,
    expected: int,
    actual: int,
    coverage: float,
    avg_score: float,
    issue_total: int,
    issue_open: int,
    issue_done_rate: float,
) -> str:
    period = f"{plan.start_date.isoformat()} 至 {plan.end_date.isoformat()}（共 {days} 天）"
    lines = [
        f"「{plan.name}」保障期间为 {period}，保障等级{plan.level}，"
        f"覆盖重点区域 {key_count} 座公厕，累计安排值守 {duty_total} 个班次。",
        f"按每公厕每日 {plan.inspections_per_day} 次标准应巡查 {expected} 次，"
        f"实际完成 {actual} 次，巡查覆盖率 {coverage}%，期间巡查平均得分 {avg_score} 分。",
        f"保障期间共上报问题 {issue_total} 件，整改率 {issue_done_rate}%，"
        f"期末未闭环 {issue_open} 件。",
    ]
    if issue_open:
        lines.append("未闭环问题需继续跟踪整改，直至验收闭环。")
    else:
        lines.append("保障期间问题均已闭环，保障任务圆满完成。")
    return "".join(lines)


def build_summary(db: Session, plan: SupportPlan) -> SupportSummary:
    """汇总保障期间的巡查、值守与问题数据，出具保障情况小结。"""
    start_dt, end_dt = _period_bounds(plan)
    restrooms = key_restrooms(db, plan)
    restroom_ids = [room.id for room in restrooms]
    days = (plan.end_date - plan.start_date).days + 1

    expected = days * len(restroom_ids) * plan.inspections_per_day
    actual = 0
    avg_score = 0.0
    if restroom_ids:
        actual = db.scalar(
            select(func.count())
            .select_from(Inspection)
            .where(
                Inspection.restroom_id.in_(restroom_ids),
                Inspection.inspect_time >= start_dt,
                Inspection.inspect_time <= end_dt,
            )
        ) or 0
        avg_score = float(
            db.scalar(
                select(func.avg(Inspection.score)).where(
                    Inspection.restroom_id.in_(restroom_ids),
                    Inspection.inspect_time >= start_dt,
                    Inspection.inspect_time <= end_dt,
                )
            )
            or 0.0
        )
    coverage = round(actual / expected * 100, 1) if expected else 0.0

    issue_stmt = select(Issue).where(
        Issue.report_time >= start_dt,
        Issue.report_time <= end_dt,
    )
    if restroom_ids:
        issue_stmt = issue_stmt.where(Issue.restroom_id.in_(restroom_ids))
    else:
        issue_stmt = issue_stmt.where(Issue.id.is_(None))
    issues = list(db.scalars(issue_stmt))

    issue_total = len(issues)
    open_issues = [issue for issue in issues if issue.status in OPEN_ISSUE_STATUSES]
    done_count = sum(
        1 for issue in issues if issue.status in (IssueStatus.DONE.value, IssueStatus.CLOSED.value)
    )
    issue_done_rate = round(done_count / issue_total * 100, 1) if issue_total else 0.0

    category_counts = {category.value: 0 for category in IssueCategory}
    severity_counts = {severity.value: 0 for severity in IssueSeverity}
    for issue in issues:
        if issue.category in category_counts:
            category_counts[issue.category] += 1
        if issue.severity in severity_counts:
            severity_counts[issue.severity] += 1

    open_issues.sort(key=lambda issue: issue.report_time, reverse=True)
    plan_out = to_out(db, plan)
    return SupportSummary(
        plan=plan_out,
        key_restroom_count=len(restroom_ids),
        duty_total=len(plan.duties),
        duty_staff_total=len(plan.duties),
        expected_inspections=expected,
        actual_inspections=actual,
        coverage_rate=coverage,
        avg_score=round(avg_score, 1),
        issue_total=issue_total,
        issue_open=len(open_issues),
        issue_done_rate=issue_done_rate,
        issue_by_category=[
            NameValue(name=name, value=float(count)) for name, count in category_counts.items()
        ],
        issue_by_severity=[
            NameValue(name=name, value=float(count)) for name, count in severity_counts.items()
        ],
        open_issues=[IssueOut.model_validate(issue) for issue in open_issues[:10]],
        summary_text=_build_summary_text(
            plan,
            days=days,
            key_count=len(restroom_ids),
            duty_total=len(plan.duties),
            expected=expected,
            actual=actual,
            coverage=coverage,
            avg_score=round(avg_score, 1),
            issue_total=issue_total,
            issue_open=len(open_issues),
            issue_done_rate=issue_done_rate,
        ),
    )
