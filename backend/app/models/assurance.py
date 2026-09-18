"""节假日 / 重大活动保障值守模型。"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import (
    AssuranceLevel,
    AssuranceStatus,
    AssuranceType,
)
from app.core.database import Base


class Assurance(Base):
    """一次节假日或重大活动保障任务，含时段、等级、重点对象与保障要求。"""

    __tablename__ = "assurances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="保障编号")
    name: Mapped[str] = mapped_column(String(120), index=True, comment="保障名称")
    assurance_type: Mapped[str] = mapped_column(
        String(30), default=AssuranceType.HOLIDAY.value, index=True, comment="保障类型"
    )
    level: Mapped[str] = mapped_column(
        String(20), default=AssuranceLevel.LEVEL2.value, index=True, comment="保障等级"
    )
    status: Mapped[str] = mapped_column(
        String(20), default=AssuranceStatus.PREPARING.value, index=True, comment="保障状态"
    )
    start_date: Mapped[date] = mapped_column(Date, index=True, comment="保障开始日期")
    end_date: Mapped[date] = mapped_column(Date, index=True, comment="保障结束日期")
    daily_count: Mapped[int] = mapped_column(Integer, default=4, comment="每座重点公厕每日巡查次数")
    shift_plan: Mapped[dict] = mapped_column(
        JSON, default=dict, comment="各班次应巡次数快照 {早班:n,中班:n,晚班:n}"
    )
    requirements: Mapped[list] = mapped_column(JSON, default=list, comment="保障要求清单")
    contact: Mapped[str] = mapped_column(String(60), default="", comment="值班联络人")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    action_log: Mapped[list] = mapped_column(
        JSON, default=list, comment="保障操作记录 [{action,operator,remark,at}]"
    )
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="保障情况小结快照")
    summary_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="小结生成时间"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="启动时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="结束时间")
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="取消时间"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )

    targets: Mapped[list["AssuranceTarget"]] = relationship(
        back_populates="assurance", cascade="all, delete-orphan"
    )
    duties: Mapped[list["AssuranceDuty"]] = relationship(
        back_populates="assurance", cascade="all, delete-orphan"
    )
    issues: Mapped[list["Issue"]] = relationship(  # noqa: F821
        back_populates="assurance"
    )

    __table_args__ = (Index("ix_assurance_status_dates", "status", "start_date", "end_date"),)


class AssuranceTarget(Base):
    """保障重点对象快照：由重点区域展开并可追加个别重点公厕。"""

    __tablename__ = "assurance_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assurance_id: Mapped[int] = mapped_column(
        ForeignKey("assurances.id", ondelete="CASCADE"), index=True, comment="所属保障"
    )
    restroom_id: Mapped[int] = mapped_column(
        ForeignKey("restrooms.id", ondelete="CASCADE"), index=True, comment="重点公厕"
    )
    source: Mapped[str] = mapped_column(String(20), comment="纳入方式（区域纳入/手动指定）")
    district: Mapped[str] = mapped_column(String(60), default="", comment="所属区域快照")

    assurance: Mapped["Assurance"] = relationship(back_populates="targets")
    restroom: Mapped["Restroom"] = relationship(lazy="joined")  # noqa: F821

    __table_args__ = (
        UniqueConstraint("assurance_id", "restroom_id", name="uq_assurance_restroom"),
    )


class AssuranceDuty(Base):
    """值守岗位：保障期内 天 × 班次 × 重点公厕 的加密巡查值守安排。"""

    __tablename__ = "assurance_duties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assurance_id: Mapped[int] = mapped_column(
        ForeignKey("assurances.id", ondelete="CASCADE"), index=True, comment="所属保障"
    )
    restroom_id: Mapped[int] = mapped_column(
        ForeignKey("restrooms.id", ondelete="CASCADE"), index=True, comment="值守公厕"
    )
    duty_date: Mapped[date] = mapped_column(Date, index=True, comment="值守日期")
    shift: Mapped[str] = mapped_column(String(20), comment="值守班次")
    planned_count: Mapped[int] = mapped_column(Integer, default=1, comment="该班次应巡次数")
    assignee: Mapped[str] = mapped_column(String(60), default="", index=True, comment="值守人")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="岗位备注")

    assurance: Mapped["Assurance"] = relationship(back_populates="duties")
    restroom: Mapped["Restroom"] = relationship(lazy="joined")  # noqa: F821

    __table_args__ = (
        UniqueConstraint(
            "assurance_id", "duty_date", "shift", "restroom_id", name="uq_duty_slot"
        ),
        Index("ix_duty_restroom_date_shift", "restroom_id", "duty_date", "shift"),
    )
