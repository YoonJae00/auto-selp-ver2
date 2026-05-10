from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from datetime import datetime
from database import Base

class Prompt(Base):
    __tablename__ = "prompts"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    template: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
