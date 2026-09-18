"""业务枚举与规则常量。"""

from enum import StrEnum


class RestroomStatus(StrEnum):
    NORMAL = "正常开放"
    MAINTENANCE = "维修中"
    CLOSED = "暂停使用"


class RestroomGrade(StrEnum):
    FIRST = "一类"
    SECOND = "二类"
    THIRD = "三类"


class Shift(StrEnum):
    MORNING = "早班"
    MIDDLE = "中班"
    NIGHT = "晚班"


class AssuranceType(StrEnum):
    """保障类型：节假日 / 重大活动 / 其他。"""

    HOLIDAY = "节假日保障"
    EVENT = "重大活动保障"
    OTHER = "其他保障"


class AssuranceLevel(StrEnum):
    """保障等级，等级越高加密频次越高。"""

    LEVEL1 = "一级保障"
    LEVEL2 = "二级保障"
    LEVEL3 = "三级保障"


class AssuranceStatus(StrEnum):
    """保障生命周期状态。"""

    PREPARING = "筹备中"
    ACTIVE = "保障中"
    FINISHED = "已结束"
    CANCELLED = "已取消"


class InspectionResult(StrEnum):
    NORMAL = "正常"
    ABNORMAL = "发现问题"


class IssueCategory(StrEnum):
    CLEANING = "保洁不到位"
    FACILITY = "设施损坏"
    ODOR = "异味扰民"
    CONSUMABLE = "耗材缺失"
    SAFETY = "安全隐患"
    OTHER = "其他"


class IssueSeverity(StrEnum):
    NORMAL = "一般"
    SERIOUS = "严重"
    URGENT = "紧急"


class IssueStatus(StrEnum):
    PENDING = "待整改"
    PROCESSING = "整改中"
    REVIEWING = "待验收"
    DONE = "已完成"
    CLOSED = "已关闭"


# 整改流转规则：当前状态 -> 允许流转到的状态
ISSUE_TRANSITIONS: dict[str, list[str]] = {
    IssueStatus.PENDING: [IssueStatus.PROCESSING, IssueStatus.CLOSED],
    IssueStatus.PROCESSING: [IssueStatus.REVIEWING, IssueStatus.CLOSED],
    IssueStatus.REVIEWING: [IssueStatus.DONE, IssueStatus.PROCESSING],
    IssueStatus.DONE: [IssueStatus.CLOSED],
    IssueStatus.CLOSED: [],
}

# 状态流转对应的动作名称，用于生成整改流水
TRANSITION_ACTIONS: dict[tuple[str, str], str] = {
    (IssueStatus.PENDING, IssueStatus.PROCESSING): "开始整改",
    (IssueStatus.PENDING, IssueStatus.CLOSED): "作废关闭",
    (IssueStatus.PROCESSING, IssueStatus.REVIEWING): "提交验收",
    (IssueStatus.PROCESSING, IssueStatus.CLOSED): "终止关闭",
    (IssueStatus.REVIEWING, IssueStatus.DONE): "验收通过",
    (IssueStatus.REVIEWING, IssueStatus.PROCESSING): "验收驳回",
    (IssueStatus.DONE, IssueStatus.CLOSED): "归档关闭",
}

# 巡查检查项，每项 0-10 分
INSPECTION_CHECK_ITEMS: list[str] = [
    "地面与台阶清洁",
    "便池蹲位清洁",
    "洗手台与镜面",
    "通风除臭",
    "耗材补充",
    "垃圾清运",
    "工具与标识摆放",
    "墙面门窗卫生",
]

INSPECTION_ITEM_MAX_SCORE = 10

GRADE_EXCELLENT = "优秀"
GRADE_GOOD = "良好"
GRADE_PASS = "合格"
GRADE_FAIL = "不合格"

# 仍处于整改闭环中的状态，用于统计未整改问题
OPEN_ISSUE_STATUSES: list[str] = [
    IssueStatus.PENDING,
    IssueStatus.PROCESSING,
    IssueStatus.REVIEWING,
]

# 单检查项低于该分数视为不合格项
INSPECTION_ITEM_PROBLEM_THRESHOLD = 6


# --------------------------------------------------------------------------- #
# 节假日 / 重大活动保障
# --------------------------------------------------------------------------- #

# 保障状态流转规则：当前状态 -> 允许流转到的状态
ASSURANCE_TRANSITIONS: dict[str, list[str]] = {
    AssuranceStatus.PREPARING: [AssuranceStatus.ACTIVE, AssuranceStatus.CANCELLED],
    AssuranceStatus.ACTIVE: [AssuranceStatus.FINISHED, AssuranceStatus.CANCELLED],
    AssuranceStatus.FINISHED: [],
    AssuranceStatus.CANCELLED: [],
}

# 各状态流转对应的动作名称，用于生成保障操作记录
ASSURANCE_TRANSITION_ACTIONS: dict[tuple[str, str], str] = {
    (AssuranceStatus.PREPARING, AssuranceStatus.ACTIVE): "启动保障",
    (AssuranceStatus.PREPARING, AssuranceStatus.CANCELLED): "取消保障",
    (AssuranceStatus.ACTIVE, AssuranceStatus.FINISHED): "结束保障",
    (AssuranceStatus.ACTIVE, AssuranceStatus.CANCELLED): "终止保障",
}

# 各等级保障下，单座重点公厕每日巡查次数及按班次的分配
ASSURANCE_SHIFT_PLAN: dict[str, dict] = {
    AssuranceLevel.LEVEL1.value: {
        "daily": 6,
        "by_shift": {Shift.MORNING.value: 2, Shift.MIDDLE.value: 2, Shift.NIGHT.value: 2},
    },
    AssuranceLevel.LEVEL2.value: {
        "daily": 4,
        "by_shift": {Shift.MORNING.value: 2, Shift.MIDDLE.value: 1, Shift.NIGHT.value: 1},
    },
    AssuranceLevel.LEVEL3.value: {
        "daily": 3,
        "by_shift": {Shift.MORNING.value: 1, Shift.MIDDLE.value: 1, Shift.NIGHT.value: 1},
    },
}

# 班次排布顺序
ASSURANCE_SHIFT_ORDER: list[str] = [Shift.MORNING.value, Shift.MIDDLE.value, Shift.NIGHT.value]

# 保障等级排序权重，数值越小等级越高，多保障重叠时优先归属高等级
ASSURANCE_LEVEL_RANK: dict[str, int] = {
    AssuranceLevel.LEVEL1.value: 1,
    AssuranceLevel.LEVEL2.value: 2,
    AssuranceLevel.LEVEL3.value: 3,
}

# 仍可被问题自动归属命中的保障状态
ASSURANCE_ACTIVE_STATUSES: list[str] = [AssuranceStatus.PREPARING, AssuranceStatus.ACTIVE]

# 重点对象来源
TARGET_SOURCE_DISTRICT = "区域纳入"
TARGET_SOURCE_MANUAL = "手动指定"

# 每日每厕巡查次数允许手动微调的范围
ASSURANCE_DAILY_MIN = 3
ASSURANCE_DAILY_MAX = 12
# 单次保障最长天数，控制值守岗位的笛卡尔规模
ASSURANCE_MAX_DAYS = 62
