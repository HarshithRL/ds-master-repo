"""SQLAlchemy ORM models for Mate hub, users, projects, artifacts, and chunks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Base(DeclarativeBase):
    pass


class HubModule(Base):
    __tablename__ = "hub_module"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    icon: Mapped[str | None] = mapped_column(String)
    path: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    user_grants: Mapped[list[UserModule]] = relationship(back_populates="module")
    projects: Mapped[list[Project]] = relationship(back_populates="module")


class AppUser(Base):
    __tablename__ = "app_user"

    workspace_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_name: Mapped[str | None] = mapped_column(String)
    display_name: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)

    module_grants: Mapped[list[UserModule]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    projects: Mapped[list[Project]] = relationship(back_populates="owner")
    artifacts: Mapped[list[Artifact]] = relationship(back_populates="uploader")


class UserModule(Base):
    __tablename__ = "user_module"
    __table_args__ = (
        UniqueConstraint("workspace_id", "module_id", name="uq_user_module"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("app_user.workspace_id", ondelete="CASCADE"),
        primary_key=True,
    )
    module_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("hub_module.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    granted_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)

    user: Mapped[AppUser] = relationship(back_populates="module_grants")
    module: Mapped[HubModule] = relationship(back_populates="user_grants")


class Project(Base):
    __tablename__ = "project"
    __table_args__ = (
        Index("ix_project_owner_id", "owner_id"),
        Index("ix_project_module_owner", "module_id", "owner_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    owner_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("app_user.workspace_id", ondelete="RESTRICT"),
        nullable=False,
    )
    module_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("hub_module.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    workflow_entry_point: Mapped[str | None] = mapped_column(String)
    business_process: Mapped[str | None] = mapped_column(String)
    requester: Mapped[str | None] = mapped_column(String)
    dept: Mapped[str | None] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String)
    region: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, default="Active")
    priority: Mapped[str] = mapped_column(String, nullable=False, default="Medium")
    budget: Mapped[str | None] = mapped_column(String)
    award_horizon: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deadline: Mapped[str | None] = mapped_column(String)
    requirements_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)

    owner: Mapped[AppUser] = relationship(back_populates="projects")
    module: Mapped[HubModule] = relationship(back_populates="projects")
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    chunks: Mapped[list[Chunk]] = relationship(back_populates="project")


class Artifact(Base):
    __tablename__ = "artifact"
    __table_args__ = (
        Index("ix_artifact_project_folder", "project_id", "folder"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False,
    )
    uploaded_by: Mapped[str] = mapped_column(
        String,
        ForeignKey("app_user.workspace_id", ondelete="RESTRICT"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    folder: Mapped[str | None] = mapped_column(String)
    original_name: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    storage_relpath: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    parsed_json: Mapped[str | None] = mapped_column(Text)
    parse_status: Mapped[str | None] = mapped_column(String)
    parse_error: Mapped[str | None] = mapped_column(Text)
    parsed_relpath: Mapped[str | None] = mapped_column(String)
    vendor_id: Mapped[str | None] = mapped_column(String)
    doc_role: Mapped[str | None] = mapped_column(String)
    role_confidence: Mapped[float | None] = mapped_column(Float)
    content_hash: Mapped[str | None] = mapped_column(String)
    superseded_by: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)

    project: Mapped[Project] = relationship(back_populates="artifacts")
    uploader: Mapped[AppUser] = relationship(back_populates="artifacts")
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="artifact",
        cascade="all, delete-orphan",
    )


class Chunk(Base):
    __tablename__ = "chunk"
    __table_args__ = (
        UniqueConstraint("artifact_id", "ordinal", name="uq_chunk_artifact_ordinal"),
        Index("ix_chunk_project_id", "project_id"),
        Index("ix_chunk_artifact_ordinal", "artifact_id", "ordinal"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("artifact.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_type: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    heading_path_json: Mapped[str | None] = mapped_column(Text)
    block_ids_json: Mapped[str | None] = mapped_column(Text)
    location_json: Mapped[str | None] = mapped_column(Text)
    table_json: Mapped[str | None] = mapped_column(Text)
    page_kind: Mapped[str | None] = mapped_column(String)
    reconstructor: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)

    project: Mapped[Project] = relationship(back_populates="chunks")
    artifact: Mapped[Artifact] = relationship(back_populates="chunks")


EVIDENCE_STATUSES = (
    "met",
    "partial",
    "not_offered",
    "not_stated",
    "unclear",
    "extraction_failed",
)
KB_NODE_TYPES = (
    "LegalEntity",
    "Bid",
    "Person",
    "Requirement",
    "Control",
    "Evidence",
    "Artifact",
    "PricingOffer",
    "Scope",
)
KB_EDGE_TYPES = (
    "BIDS_ON",
    "MEMBER_OF_CONSORTIUM",
    "PARENT_OF",
    "EMPLOYS",
    "ASSIGNED_ROLE",
    "SUBCONTRACTS_TO",
    "RESPONDS_TO",
    "CITES",
    "IN_SCOPE_FOR",
    "SUPERSEDES",
    "CONFLICTS_WITH",
)
PRICING_OFFER_TYPES = ("fixed_price", "time_and_materials")


class Vendor(Base):
    __tablename__ = "vendor"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    legal_entity: Mapped[str | None] = mapped_column(String)
    registry_id: Mapped[str | None] = mapped_column(String)
    status: Mapped[str | None] = mapped_column(String, default="bidder")
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)


class Requirement(Base):
    __tablename__ = "requirement"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str | None] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String)
    weight: Mapped[float | None] = mapped_column(Float)
    mandatory: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_artifact_id: Mapped[str | None] = mapped_column(String)
    source_page: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint(
            "requirement_id", "vendor_id", "model_version", name="uq_evidence_req_vendor_model"
        ),
        CheckConstraint(
            "status IN ('met','partial','not_offered','not_stated','unclear','extraction_failed')",
            name="ck_evidence_status",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    requirement_id: Mapped[str] = mapped_column(String, nullable=False)
    vendor_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    claim_text: Mapped[str | None] = mapped_column(Text)
    artifact_id: Mapped[str | None] = mapped_column(String)
    chunk_id: Mapped[str | None] = mapped_column(String)
    page: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float | None] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String, nullable=False)
    extracted_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)
    reviewed_by: Mapped[str | None] = mapped_column(String)
    reviewed_at: Mapped[str | None] = mapped_column(String)


class PricingLine(Base):
    __tablename__ = "pricing_line"
    __table_args__ = (
        CheckConstraint(
            "offer_type IN ('fixed_price','time_and_materials')",
            name="ck_pricing_offer_type",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String)
    vendor_id: Mapped[str | None] = mapped_column(String)
    offer_type: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str | None] = mapped_column(String)
    seniority: Mapped[str | None] = mapped_column(String)
    rate: Mapped[float | None] = mapped_column(Numeric)
    rate_unit: Mapped[str | None] = mapped_column(String)
    currency: Mapped[str | None] = mapped_column(String)
    quantity: Mapped[float | None] = mapped_column(Numeric)
    line_total: Mapped[float | None] = mapped_column(Numeric)
    etex_effort_days: Mapped[float | None] = mapped_column(Numeric)
    etex_effort_side: Mapped[str | None] = mapped_column(String)
    discount_terms: Mapped[str | None] = mapped_column(Text)
    annexe_a02_completed: Mapped[int | None] = mapped_column(Integer)
    artifact_id: Mapped[str | None] = mapped_column(String)
    page: Mapped[int | None] = mapped_column(Integer)
    chunk_id: Mapped[str | None] = mapped_column(String)
    verified: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_version: Mapped[str] = mapped_column(String, nullable=False)


class BidProfileRow(Base):
    __tablename__ = "bid_profile"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "vendor_id", "model_version", name="uq_bid_profile"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    vendor_id: Mapped[str] = mapped_column(String, nullable=False)
    facts_json: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(String, nullable=False)
    extracted_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)


class KbNode(Base):
    __tablename__ = "kb_node"
    __table_args__ = (
        CheckConstraint(
            "type IN ('LegalEntity','Bid','Person','Requirement','Control','Evidence','Artifact','PricingOffer','Scope')",
            name="ck_kb_node_type",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    props: Mapped[str | None] = mapped_column(Text)
    source_artifact_id: Mapped[str | None] = mapped_column(String)
    source_page: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float | None] = mapped_column(Float)
    model_version: Mapped[str | None] = mapped_column(String)


class KbEdge(Base):
    __tablename__ = "kb_edge"
    __table_args__ = (
        CheckConstraint(
            "type IN ('BIDS_ON','MEMBER_OF_CONSORTIUM','PARENT_OF','EMPLOYS','ASSIGNED_ROLE',"
            "'SUBCONTRACTS_TO','RESPONDS_TO','CITES','IN_SCOPE_FOR','SUPERSEDES','CONFLICTS_WITH')",
            name="ck_kb_edge_type",
        ),
        Index("ix_edge_src", "project_id", "src", "type"),
        Index("ix_edge_dst", "project_id", "dst", "type"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    src: Mapped[str] = mapped_column(String, ForeignKey("kb_node.id"), nullable=False)
    dst: Mapped[str] = mapped_column(String, ForeignKey("kb_node.id"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    props: Mapped[str | None] = mapped_column(Text)
    source_artifact_id: Mapped[str | None] = mapped_column(String)
    source_page: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float | None] = mapped_column(Float)
    model_version: Mapped[str | None] = mapped_column(String)


class ChatSession(Base):
    __tablename__ = "chat_session"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False, default="New chat")
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)


class ChatMessage(Base):
    __tablename__ = "chat_message"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)


class OntologyRequirement(Base):
    __tablename__ = "ontology_requirement"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    req_id: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String, nullable=False)
    target: Mapped[str | None] = mapped_column(Text)
    mandatory: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    weight: Mapped[float | None] = mapped_column(Float)
    ontology_version: Mapped[str] = mapped_column(String, nullable=False)


class OntologyOffering(Base):
    __tablename__ = "ontology_offering"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    vendor_id: Mapped[str] = mapped_column(String, nullable=False)
    req_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="?")
    value_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    numeric_value: Mapped[float | None] = mapped_column(Float)
    locator: Mapped[str] = mapped_column(String, nullable=False, default="")
    quote: Mapped[str] = mapped_column(Text, nullable=False, default="")
    chunk_id: Mapped[str | None] = mapped_column(String)
    confidence: Mapped[float | None] = mapped_column(Float)


class TcoLine(Base):
    __tablename__ = "tco_line"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    vendor_id: Mapped[str] = mapped_column(String, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    line_type: Mapped[str] = mapped_column(String, nullable=False)
    amount_eur: Mapped[float | None] = mapped_column(Float)
    mandays: Mapped[float | None] = mapped_column(Float)
    rate_eur_per_day: Mapped[float | None] = mapped_column(Float)
    derived: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locator: Mapped[str] = mapped_column(String, nullable=False, default="")
    note: Mapped[str | None] = mapped_column(Text)


class OntologyFlag(Base):
    __tablename__ = "ontology_flag"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    vendors_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    locator: Mapped[str | None] = mapped_column(String)


class Pack(Base):
    __tablename__ = "pack"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="idle")
    path: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)


class QualityFlag(Base):
    __tablename__ = "quality_flag"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String)
    artifact_id: Mapped[str | None] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)


class KbBuildJob(Base):
    """Durable kb_build run record.

    The legacy in-process thread leaves no trace if the app restarts mid-build,
    so a project can sit on "building" forever. A row here plus `heartbeat_at`
    makes a dead run detectable instead of indistinguishable from a slow one.
    """

    __tablename__ = "kb_build_job"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    mode: Mapped[str] = mapped_column(String, nullable=False, default="thread")
    run_id: Mapped[str | None] = mapped_column(String)
    message: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    heartbeat_at: Mapped[str | None] = mapped_column(String)
    started_at: Mapped[str | None] = mapped_column(String)
    finished_at: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)


def identity_user_payload(user: dict[str, Any] | None) -> dict[str, str | None]:
    if not isinstance(user, dict):
        return {
            "workspace_id": "",
            "user_name": None,
            "display_name": None,
            "email": None,
        }
    return {
        "workspace_id": str(user.get("id") or "").strip(),
        "user_name": _optional_str(user.get("user_name")),
        "display_name": _optional_str(user.get("display_name")),
        "email": _optional_str(user.get("email")),
    }


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
