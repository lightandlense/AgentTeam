from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, TIMESTAMP, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class Client(Base):
    __tablename__ = "clients"

    client_id: Mapped[str] = mapped_column(Text, primary_key=True)
    business_name: Mapped[str] = mapped_column(Text, nullable=False)
    business_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="America/Chicago"
    )
    owner_email: Mapped[str] = mapped_column(Text, nullable=False)
    twilio_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    retell_agent_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    services: Mapped[Any] = mapped_column(
        JSONB, nullable=True, server_default="'[]'::jsonb"
    )
    hours: Mapped[Any] = mapped_column(
        JSONB, nullable=True, server_default="'{}'::jsonb"
    )
    working_days: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default="{1,2,3,4,5}"
    )
    business_hours: Mapped[Any] = mapped_column(
        JSONB, nullable=False, server_default='\'{"start": "09:00", "end": "17:00"}\''
    )
    slot_duration_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="60"
    )
    buffer_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    lead_time_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="60"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("clients.client_id", ondelete="CASCADE"),
        nullable=False,
    )
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_expiry: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("clients.client_id", ondelete="CASCADE"),
        nullable=False,
    )
    doc_name: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Any] = mapped_column(Vector(1536), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("clients.client_id", ondelete="CASCADE"),
        nullable=False,
    )
    event_id: Mapped[str] = mapped_column(Text, nullable=False)
    caller_phone: Mapped[str] = mapped_column(Text, nullable=False)
    caller_name: Mapped[str] = mapped_column(Text, nullable=False)
    caller_email: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    slot_dt: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = ["Client", "OAuthToken", "Embedding", "Appointment"]
