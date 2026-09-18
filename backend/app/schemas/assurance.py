"""节假日 / 重大活动保障相关数据结构。"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.constants import (
    ASSURANCE_DAILY_MAX,
    ASSURANCE_DAILY_MIN,
    ASSURANCE_MAX_DAYS,
    AssuranceLevel,
    AssuranceStatus,
    AssuranceType,
)
from app.schemas.common import NameValue
from app.schemas.restroom import RestroomBrief


class AssuranceBrief(BaseModel):
    """问题引用所属保障时的精简信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    level: str
    status: str


class AssuranceTargetOut(BaseModel):
    """保障重点对象。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    restroom_id: int
    source: str
    district: str = ""
    restroom: RestroomBrief | None = None


class AssuranceBase(BaseModel):
    name: str = Field(min_length=1, max_length=120, description="保障名称")
    assurance_type: AssuranceType = Field(default=AssuranceType.HOLIDAY, description="保障类型")
    level: AssuranceLevel = Field(default=AssuranceLevel.LEVEL2, description="保障等级")
    start_date: date = Field(description="保障开始日期")
    end_date: date = Field(description="保障结束日期")
    districts: list[str] = Field(default_factory=list, description="重点区域，区域内正常开放公厕全部纳入")
    restroom_ids: list[int] = Field(default_factory=list, description="额外追加的重点公厕")
    daily_count: int | None = Field(
        default=None,
        ge=ASSURANCE_DAILY_MIN,
        le=ASSURANCE_DAILY_MAX,
        description="每座重点公厕每日巡查次数，留空按等级预置",
    )
    requirements: list[str] = Field(default_factory=list, description="保障要求清单")
    contact: str = Field(default="", max_length=60, description="值班联络人")
    remark: str | None = Field(default=None, max_length=500, description="备注")

    @field_validator("districts", "restroom_ids", mode="before")
    @classmethod
    def _dedupe(cls, value):
        if value is None:
            return []
        return list(dict.fromkeys(value))

    @field_validator("districts", mode="after")
    @classmethod
    def _strip_districts(cls, value):
        return [item.strip() for item in value if item and item.strip()]

    @field_validator("requirements", mode="after")
    @classmethod
    def _clean_requirements(cls, value):
        cleaned = [item.strip() for item in (value or []) if item and item.strip()]
        for item in cleaned:
            if len(item) > 200:
                raise ValueError("单条保障要求不能超过 200 字")
        return cleaned

    @model_validator(mode="after")
    def _check_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("保障结束日期不能早于开始日期")
        if (self.end_date - self.start_date).days + 1 > ASSURANCE_MAX_DAYS:
            raise ValueError(f"单次保障时段不能超过 {ASSURANCE_MAX_DAYS} 天")
        return self


class AssuranceCreate(AssuranceBase):
    pass


class AssuranceUpdate(BaseModel):
    """局部更新；仅「筹备中」允许修改时段/等级/重点对象等结构性字段。"""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    assurance_type: AssuranceType | None = None
    level: AssuranceLevel | None = None
    start_date: date | None = None
    end_date: date | None = None
    districts: list[str] | None = None
    restroom_ids: list[int] | None = None
    daily_count: int | None = Field(default=None, ge=ASSURANCE_DAILY_MIN, le=ASSURANCE_DAILY_MAX)
    requirements: list[str] | None = None
    contact: str | None = Field(default=None, max_length=60)
    remark: str | None = Field(default=None, max_length=500)


class AssuranceDutyOut(BaseModel):
    """单个值守岗位及其实际到岗情况。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    restroom_id: int
    restroom: RestroomBrief | None = None
    duty_date: date
    shift: str
    planned_count: int
    actual_count: int = 0
    completed: bool = False
    assignee: str = ""
    remark: str | None = None


class AssuranceDutyUpdate(BaseModel):
    assignee: str | None = Field(default=None, max_length=60, description="值守人，传空串清空")
    remark: str | None = Field(default=None, max_length=500)


class AssuranceProgress(BaseModel):
    """值守与加密巡查的完成进度，仅统计截至 as_of 应到的岗位。"""

    as_of: date
    total_days: int = 0
    target_count: int = 0
    due_duty_count: int = 0
    completed_duty_count: int = 0
    duty_completion_rate: float = 0.0
    planned_inspection_count: int = 0
    actual_inspection_count: int = 0
    inspection_completion_rate: float = 0.0


class AssuranceSummaryIssue(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    title: str
    restroom_name: str = ""
    district: str = ""
    category: str = ""
    severity: str = ""
    status: str = ""
    deadline: datetime | None = None


class AssuranceSummary(BaseModel):
    """保障结束后出具的保障情况小结（结构化快照）。"""

    generated_at: datetime
    name: str
    code: str
    assurance_type: str
    level: str
    start_date: date
    end_date: date
    days: int
    districts: list[str] = Field(default_factory=list)
    district_count: int = 0
    target_count: int = 0
    duty_planned: int = 0
    duty_due: int = 0
    duty_completed: int = 0
    duty_completion_rate: float = 0.0
    inspection_planned: int = 0
    inspection_actual: int = 0
    inspection_completion_rate: float = 0.0
    avg_score: float | None = None
    issue_total: int = 0
    issue_open: int = 0
    issue_closed: int = 0
    issue_overdue: int = 0
    issue_by_category: list[NameValue] = Field(default_factory=list)
    issue_by_severity: list[NameValue] = Field(default_factory=list)
    issue_by_district: list[NameValue] = Field(default_factory=list)
    open_items: list[AssuranceSummaryIssue] = Field(default_factory=list)


class AssuranceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    assurance_type: str
    level: str
    status: str
    start_date: date
    end_date: date
    daily_count: int
    shift_plan: dict = Field(default_factory=dict)
    requirements: list[str] = Field(default_factory=list)
    contact: str = ""
    remark: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancelled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    target_count: int = 0
    district_count: int = 0


class AssuranceDetail(AssuranceOut):
    targets: list[AssuranceTargetOut] = Field(default_factory=list)
    progress: AssuranceProgress | None = None
    issue_total: int = 0
    issue_open: int = 0
    summary: AssuranceSummary | None = None
    summary_generated_at: datetime | None = None
    action_log: list[dict] = Field(default_factory=list)


class AssuranceAction(BaseModel):
    """启动 / 结束 / 取消保障。"""

    operator: str = Field(min_length=1, max_length=60, description="操作人")
    remark: str | None = Field(default=None, max_length=500, description="操作说明")


class RelinkOut(BaseModel):
    relinked: int
