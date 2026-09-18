"""节假日与重大活动保障相关数据结构。"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.constants import SupportCategory, SupportLevel
from app.schemas.issue import IssueOut
from app.schemas.restroom import RestroomBrief
from app.schemas.stats import NameValue


class SupportPlanBase(BaseModel):
    name: str = Field(min_length=1, max_length=120, description="保障名称")
    category: SupportCategory = Field(default=SupportCategory.HOLIDAY, description="保障类型")
    level: SupportLevel = Field(default=SupportLevel.SECOND, description="保障等级")
    start_date: date = Field(description="保障开始日期")
    end_date: date = Field(description="保障结束日期")
    districts: list[str] = Field(default_factory=list, description="重点区域（按区域）")
    restroom_ids: list[int] = Field(default_factory=list, description="重点公厕")
    requirements: str = Field(default="", max_length=1000, description="保障要求")
    inspections_per_day: int | None = Field(
        default=None, ge=1, le=10, description="每公厕每日巡查频次，留空按等级自动确定"
    )
    staff_pool: list[str] = Field(default_factory=list, description="值守人员名单")

    @model_validator(mode="after")
    def _check_date_range(self) -> "SupportPlanBase":
        if self.end_date < self.start_date:
            raise ValueError("保障结束日期不能早于开始日期")
        return self


class SupportPlanCreate(SupportPlanBase):
    code: str | None = Field(default=None, max_length=32, description="保障编号，留空自动生成")


class SupportPlanUpdate(BaseModel):
    """局部更新，仅提交需要变更的字段。"""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: SupportCategory | None = None
    level: SupportLevel | None = None
    start_date: date | None = None
    end_date: date | None = None
    districts: list[str] | None = None
    restroom_ids: list[int] | None = None
    requirements: str | None = Field(default=None, max_length=1000)
    inspections_per_day: int | None = Field(default=None, ge=1, le=10)
    staff_pool: list[str] | None = None
    conclusion: str | None = Field(default=None, max_length=2000, description="保障情况小结")


class SupportDutyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    duty_date: date
    shift: str
    staff: str
    phone: str
    note: str | None = None


class SupportPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    category: str
    level: str
    start_date: date
    end_date: date
    districts: list[str] = Field(default_factory=list)
    restroom_ids: list[int] = Field(default_factory=list)
    requirements: str = ""
    inspections_per_day: int
    staff_pool: list[str] = Field(default_factory=list)
    status: str
    conclusion: str | None = None
    created_at: datetime
    updated_at: datetime
    duty_count: int = 0
    key_restroom_count: int = 0


class SupportPlanDetail(SupportPlanOut):
    """保障方案详情，附带值守安排与重点公厕清单。"""

    duties: list[SupportDutyOut] = Field(default_factory=list)
    key_restrooms: list[RestroomBrief] = Field(default_factory=list)


class SupportSummary(BaseModel):
    """保障情况小结：巡查、值守与问题的汇总统计。"""

    plan: SupportPlanOut
    key_restroom_count: int = 0
    duty_total: int = Field(default=0, description="值守班次总数")
    duty_staff_total: int = Field(default=0, description="值守人次数")
    expected_inspections: int = Field(default=0, description="应巡次数")
    actual_inspections: int = Field(default=0, description="实巡次数")
    coverage_rate: float = Field(default=0.0, description="巡查覆盖率（百分比）")
    avg_score: float = Field(default=0.0, description="保障期间巡查平均得分")
    issue_total: int = 0
    issue_open: int = Field(default=0, description="未闭环问题数")
    issue_done_rate: float = Field(default=0.0, description="问题整改率（百分比）")
    issue_by_category: list[NameValue] = Field(default_factory=list)
    issue_by_severity: list[NameValue] = Field(default_factory=list)
    open_issues: list[IssueOut] = Field(default_factory=list, description="未闭环问题清单")
    summary_text: str = Field(default="", description="自动生成的保障小结")
