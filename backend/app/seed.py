"""演示数据生成：首次启动时写入，便于快速体验各模块。"""

import random
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import (
    INSPECTION_CHECK_ITEMS,
    IssueCategory,
    IssueSeverity,
    IssueStatus,
    RestroomGrade,
    RestroomStatus,
    Shift,
)
from app.models import Restroom
from app.schemas.inspection import InspectionCreate, InspectionItem
from app.schemas.issue import IssueCreate, IssueStatusUpdate
from app.schemas.restroom import RestroomCreate
from app.services import inspection_service, issue_service, restroom_service

RANDOM_SEED = 20240913

RESTROOM_SPECS = [
    ("人民广场公共厕所", "城东区", "人民广场东侧 50 米", RestroomGrade.FIRST, RestroomStatus.NORMAL, "王秀兰", 12, 6, True),
    ("滨江公园公共厕所", "城东区", "滨江公园 3 号入口", RestroomGrade.SECOND, RestroomStatus.NORMAL, "李国强", 8, 4, True),
    ("和平路公共厕所", "城东区", "和平路与解放街交叉口", RestroomGrade.THIRD, RestroomStatus.MAINTENANCE, "赵敏", 4, 2, False),
    ("火车站南广场公共厕所", "城西区", "火车站南广场西侧", RestroomGrade.FIRST, RestroomStatus.NORMAL, "陈志远", 16, 8, True),
    ("西城集贸市场公共厕所", "城西区", "西城集贸市场北门", RestroomGrade.SECOND, RestroomStatus.NORMAL, "刘桂芳", 10, 4, False),
    ("文化路步行街公共厕所", "城西区", "文化路步行街中段", RestroomGrade.SECOND, RestroomStatus.NORMAL, "孙鹏", 9, 5, True),
    ("滨江新区体育中心公共厕所", "滨江新区", "体育中心东看台下", RestroomGrade.FIRST, RestroomStatus.NORMAL, "周晓燕", 14, 7, True),
    ("滨江新区政务中心公共厕所", "滨江新区", "政务服务中心一楼", RestroomGrade.SECOND, RestroomStatus.NORMAL, "吴建华", 8, 4, True),
    ("老城隍庙公共厕所", "老城区", "城隍庙街 12 号", RestroomGrade.THIRD, RestroomStatus.NORMAL, "郑淑珍", 5, 2, False),
    ("老城区第三小学旁公共厕所", "老城区", "第三小学东侧巷道", RestroomGrade.THIRD, RestroomStatus.CLOSED, "何伟", 4, 2, False),
]

INSPECTORS = ["张伟", "刘洋", "胡明月", "邓晨曦", "马晓峰", "杨柳"]
MANAGERS = ["王秀兰", "李国强", "陈志远", "刘桂芳", "周晓燕", "吴建华", "郑淑珍", "孙鹏"]

ISSUE_TEMPLATES = {
    IssueCategory.CLEANING: [
        "地面存在明显污渍未及时清理",
        "蹲位清洁不彻底，存在残留",
        "垃圾篓内垃圾未及时清运",
    ],
    IssueCategory.FACILITY: [
        "水龙头漏水，需更换阀芯",
        "感应冲水器失灵，无法自动冲水",
        "隔间门锁损坏无法反锁",
    ],
    IssueCategory.ODOR: [
        "公厕内异味明显，通风效果差",
        "排风扇停转导致异味积聚",
    ],
    IssueCategory.CONSUMABLE: [
        "洗手液未及时补充",
        "纸巾盒空置，未补充厕纸",
    ],
    IssueCategory.SAFETY: [
        "地面湿滑未放置防滑警示牌",
        "照明灯具损坏，夜间存在安全隐患",
    ],
    IssueCategory.OTHER: [
        "无障碍扶手松动需加固",
        "标识牌褪色需更换",
    ],
}

CATEGORY_BY_ITEM = {
    "地面与台阶清洁": IssueCategory.CLEANING,
    "便池蹲位清洁": IssueCategory.CLEANING,
    "洗手台与镜面": IssueCategory.CLEANING,
    "通风除臭": IssueCategory.ODOR,
    "耗材补充": IssueCategory.CONSUMABLE,
    "垃圾清运": IssueCategory.CLEANING,
    "工具与标识摆放": IssueCategory.OTHER,
    "墙面门窗卫生": IssueCategory.CLEANING,
}


def _build_items(rng: random.Random, quality: float) -> list[InspectionItem]:
    items: list[InspectionItem] = []
    for name in INSPECTION_CHECK_ITEMS:
        score = quality + rng.uniform(-1.6, 1.4)
        items.append(InspectionItem(name=name, score=max(0, min(10, round(score)))))
    return items


def _pick_problem(items: list[InspectionItem]) -> str | None:
    """找出最需要整改的检查项：优先取不合格项，否则取得分最低的一项。"""
    if not items:
        return None
    problems = [item for item in items if item.score < 6]
    pool = problems or items
    return min(pool, key=lambda item: item.score).name


def seed_database(db: Session, *, reset: bool = False) -> int:
    """写入演示数据，返回新增的问题条数；已有数据时默认跳过。"""
    existing = db.scalar(select(func.count()).select_from(Restroom)) or 0
    if existing and not reset:
        return 0

    rng = random.Random(RANDOM_SEED)
    now = datetime.now()

    restrooms = [
        restroom_service.create_restroom(
            db,
            RestroomCreate(
                name=name,
                district=district,
                address=address,
                grade=grade,
                status=status,
                manager=manager,
                manager_phone=f"13{rng.randint(100000000, 999999999)}",
                stall_count=stalls,
                basin_count=basins,
                has_accessible=accessible,
                open_hours="06:00-22:30" if grade == RestroomGrade.FIRST else "06:30-21:30",
            ),
        )
        for name, district, address, grade, status, manager, stalls, basins, accessible in RESTROOM_SPECS
    ]

    quality_by_restroom = {room.id: rng.uniform(7.4, 9.8) for room in restrooms}
    inspection_ids: list[tuple[int, int]] = []  # (restroom_id, inspection_id)

    for offset in range(13, -1, -1):
        day = now - timedelta(days=offset)
        for room in restrooms:
            if room.status == RestroomStatus.CLOSED:
                continue
            if rng.random() < 0.3:
                continue
            quality = quality_by_restroom[room.id] + rng.uniform(-1.0, 0.6)
            if rng.random() < 0.18:
                quality -= 2.6
            items = _build_items(rng, quality)
            inspection = inspection_service.create_inspection(
                db,
                InspectionCreate(
                    restroom_id=room.id,
                    inspector=rng.choice(INSPECTORS),
                    shift=rng.choice(list(Shift)),
                    inspect_time=day.replace(
                        hour=rng.choice([8, 10, 14, 16, 19]), minute=rng.choice([5, 20, 35, 50])
                    ),
                    items=items,
                    remark=None,
                ),
            )
            inspection_ids.append((room.id, inspection.id))

    created = 0
    for restroom_id, inspection_id in inspection_ids:
        summary = inspection_service.get_inspection(db, inspection_id)
        if summary.result != "发现问题" or rng.random() > 0.75:
            continue
        problem_item = _pick_problem([InspectionItem(**item) for item in summary.items])
        category = CATEGORY_BY_ITEM.get(problem_item or "", IssueCategory.OTHER)
        title = rng.choice(ISSUE_TEMPLATES[category])
        severity = (
            IssueSeverity.URGENT
            if category in (IssueCategory.SAFETY, IssueCategory.FACILITY) and rng.random() < 0.3
            else rng.choice([IssueSeverity.NORMAL, IssueSeverity.SERIOUS])
        )
        age_days = (now - summary.inspect_time).days
        deadline = summary.inspect_time + timedelta(
            days=1 if severity == IssueSeverity.URGENT else 3
        )
        issue = issue_service.create_issue(
            db,
            IssueCreate(
                restroom_id=restroom_id,
                inspection_id=inspection_id,
                title=title,
                description=f"巡查得分 {summary.score} 分（{summary.grade}），检查项「{problem_item}」不达标，请安排整改。",
                category=category,
                severity=severity,
                reporter=summary.inspector,
                assignee=rng.choice(MANAGERS),
                deadline=deadline,
                initial_remark="由保洁巡查自动生成的问题工单",
            ),
        )
        created += 1
        _advance_issue(db, issue.id, age_days, rng)

    _seed_assurances(db, now)

    return created


def _seed_assurances(db: Session, now: datetime) -> None:
    """节假日/重大活动保障演示数据：一个进行中的节假日保障、一个已结束并出具小结的活动保障。"""
    from app.core.constants import AssuranceLevel, AssuranceStatus, AssuranceType
    from app.schemas.assurance import AssuranceAction, AssuranceCreate
    from app.services import assurance_service

    today = now.date()

    # 进行中：节假日一级保障，覆盖城东、城西重点区域
    holiday = assurance_service.create_assurance(
        db,
        AssuranceCreate(
            name=f"{today.year}年节假日重点区域保障",
            assurance_type=AssuranceType.HOLIDAY,
            level=AssuranceLevel.LEVEL1,
            start_date=today - timedelta(days=2),
            end_date=today + timedelta(days=5),
            districts=["城东区", "城西区"],
            requirements=[
                "重点公厕每班次巡查不少于 2 次，随脏随保",
                "洗手液、厕纸等耗材备货量翻倍",
                "安排专人定点值守，发现问题 30 分钟内处置",
                "每日 18:00 前报送保障日报",
            ],
            contact="值班室 周建国",
            remark="覆盖节假日客流高峰，重点关注交通枢纽与商圈周边公厕",
        ),
    )
    assurance_service.change_status(
        db,
        holiday.id,
        AssuranceStatus.ACTIVE,
        AssuranceAction(operator="值班长 周建国", remark="保障正式启动"),
    )
    assurance_service.relink_issues(db, holiday.id)

    # 已结束：重大活动二级保障，结束时自动归集问题并生成小结
    event = assurance_service.create_assurance(
        db,
        AssuranceCreate(
            name="滨江新区秋季运动赛事保障",
            assurance_type=AssuranceType.EVENT,
            level=AssuranceLevel.LEVEL2,
            start_date=today - timedelta(days=12),
            end_date=today - timedelta(days=8),
            districts=["滨江新区"],
            requirements=["赛事时段每 2 小时巡查一次", "加强体育中心周边公厕通风除臭"],
            contact="赛事保障组 林楠",
        ),
    )
    _seed_event_issues(db, event.id, event.start_date)
    assurance_service.change_status(
        db,
        event.id,
        AssuranceStatus.ACTIVE,
        AssuranceAction(operator="林楠", remark="赛事保障启动"),
    )
    assurance_service.change_status(
        db,
        event.id,
        AssuranceStatus.FINISHED,
        AssuranceAction(operator="值班长 周建国", remark="赛事结束，保障圆满完成"),
    )


def _seed_event_issues(db: Session, event_id: int, start: date) -> None:
    """为已结束的赛事保障补充落在其窗口内的问题（含未闭环超期与已闭环），便于小结演示。"""
    from sqlalchemy import select

    from app.core.constants import IssueCategory, IssueSeverity, IssueStatus
    from app.models import Restroom
    from app.schemas.issue import IssueCreate, IssueStatusUpdate

    rooms = list(
        db.scalars(
            select(Restroom)
            .where(Restroom.district == "滨江新区")
            .order_by(Restroom.id)
        )
    )
    if len(rooms) < 2:
        return

    def _at(day_offset: int, hour: int = 9) -> datetime:
        return datetime.combine(start + timedelta(days=day_offset), datetime.min.time()).replace(
            hour=hour
        )

    # 未闭环且已超期
    issue_service.create_issue(
        db,
        IssueCreate(
            restroom_id=rooms[0].id,
            title="赛事当天人流增大，地面清洁不及时",
            description="体育中心东看台公厕中场休息时段地面有污渍。",
            category=IssueCategory.CLEANING,
            severity=IssueSeverity.SERIOUS,
            reporter="胡明月",
            assignee=rooms[0].manager,
            report_time=_at(1, 10),
            deadline=_at(2, 18),
            initial_remark="保障巡查发现，待保洁班组处理",
        ),
    )
    # 已完成闭环
    done = issue_service.create_issue(
        db,
        IssueCreate(
            restroom_id=rooms[1].id,
            title="感应冲水器失灵",
            description="政务中心一楼男卫一个感应冲水器无响应。",
            category=IssueCategory.FACILITY,
            severity=IssueSeverity.NORMAL,
            reporter="邓晨曦",
            assignee="维修班",
            report_time=_at(2, 9),
            deadline=_at(4, 18),
            initial_remark="赛事保障期间设施报修",
        ),
    )
    for target, operator, remark in [
        (IssueStatus.PROCESSING, "维修班", "已到场更换感应器"),
        (IssueStatus.REVIEWING, "维修班", "维修完成，提交验收"),
        (IssueStatus.DONE, "邓晨曦", "现场复核正常"),
    ]:
        try:
            issue_service.change_status(
                db, done.id,
                IssueStatusUpdate(to_status=target, operator=operator, remark=remark),
            )
        except Exception:  # noqa: BLE001  演示数据允许跳过
            break

    # 已关闭归档
    closed = issue_service.create_issue(
        db,
        IssueCreate(
            restroom_id=rooms[0].id,
            title="洗手液补充不及时",
            category=IssueCategory.CONSUMABLE,
            severity=IssueSeverity.NORMAL,
            reporter="张伟",
            assignee=rooms[0].manager,
            report_time=_at(3, 14),
            deadline=_at(4, 12),
        ),
    )
    for target, operator in [
        (IssueStatus.PROCESSING, "保洁班组"),
        (IssueStatus.REVIEWING, "保洁班组"),
        (IssueStatus.DONE, "张伟"),
        (IssueStatus.CLOSED, "值班长 周建国"),
    ]:
        try:
            issue_service.change_status(
                db, closed.id, IssueStatusUpdate(to_status=target, operator=operator)
            )
        except Exception:  # noqa: BLE001
            break


def _advance_issue(db: Session, issue_id: int, age_days: int, rng: random.Random) -> None:
    """按问题存在时长模拟整改进度，让看板呈现多种状态。"""
    steps: list[tuple[str, str, str]] = []
    if age_days >= 1:
        steps.append(
            (
                IssueStatus.PROCESSING.value,
                "街办保洁队",
                "已派单至保洁班组，安排当日整改",
            )
        )
    if age_days >= 3:
        steps.append(
            (
                IssueStatus.REVIEWING.value,
                "整改责任人",
                "整改完成，提交巡查员验收",
            )
        )
    if age_days >= 5 and rng.random() < 0.75:
        steps.append((IssueStatus.DONE.value, "巡查员", "现场复核通过，问题已闭环"))
    if age_days >= 8 and rng.random() < 0.6:
        steps.append((IssueStatus.CLOSED.value, "值班长", "归档关闭"))

    for target, operator, remark in steps:
        try:
            issue_service.change_status(
                db,
                issue_id,
                IssueStatusUpdate(to_status=IssueStatus(target), operator=operator, remark=remark),
            )
        except Exception:  # noqa: BLE001  演示数据允许跳过不合法的流转
            break
