"""节假日与重大活动保障模型。"""

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import SupportCategory, SupportLevel, SupportStatus
from app.core.database import Base


class SupportPlan(Base):
    """一次节假日/重大活动保障方案，含保障时段、重点区域与保障要求。"""

    __tablename__ = "support_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="保障编号")
    name: Mapped[str] = mapped_column(String(120), index=True, comment="保障名称")
    category: Mapped[str] = mapped_column(
        String(20), default=SupportCategory.HOLIDAY.value, index=True, comment="保障类型"
    )
    level: Mapped[str] = mapped_column(
        String(20), default=SupportLevel.SECOND.value, index=True, comment="保障等级"
    )
    start_date: Mapped[date] = mapped_column(Date, comment="保障开始日期")
    end_date: Mapped[date] = mapped_column(Date, comment="保障结束日期")
    districts: Mapped[list[str]] = mapped_column(JSON, default=list, comment="重点区域（按区域）")
    restroom_ids: Mapped[list[int]] = mapped_column(JSON, default=list, comment="重点公厕")
    requirements: Mapped[str] = mapped_column(Text, default="", comment="保障要求")
    inspections_per_day: Mapped[int] = mapped_column(Integer, default=2, comment="每公厕每日巡查频次")
    staff_pool: Mapped[list[str]] = mapped_column(JSON, default=list, comment="值守人员名单")
    status: Mapped[str] = mapped_column(
        String(20), default=SupportStatus.PREPARING.value, index=True, comment="保障状态"
    )
    conclusion: Mapped[str | None] = mapped_column(Text, nullable=True, comment="保障情况小结")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )

    duties: Mapped[list["SupportDuty"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="SupportDuty.duty_date, SupportDuty.id",
    )


class SupportDuty(Base):
    """保障值守安排：保障期内每天每个班次的值守人。"""

    __tablename__ = "support_duties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("support_plans.id", ondelete="CASCADE"), index=True, comment="所属保障方案"
    )
    duty_date: Mapped[date] = mapped_column(Date, index=True, comment="值守日期")
    shift: Mapped[str] = mapped_column(String(20), comment="班次")
    staff: Mapped[str] = mapped_column(String(60), comment="值守人员")
    phone: Mapped[str] = mapped_column(String(30), default="", comment="联系电话")
    note: Mapped[str | None] = mapped_column(Text, nullable=True, comment="值守备注")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    plan: Mapped["SupportPlan"] = relationship(back_populates="duties")
