"""Base de conocimiento RAG: documentos y chunks con embedding (pgvector) y tsvector en español."""

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Computed, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.config import get_settings
from app.models.base import Base, ConCreacion

DIM = get_settings().embed_dim


class Documento(ConCreacion, Base):
    __tablename__ = "documentos"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), index=True, comment="p. ej. DOC-OPS-2026-03")
    titulo: Mapped[str] = mapped_column(String(200))
    tipo: Mapped[str] = mapped_column(String(40))
    fuente: Mapped[str] = mapped_column(String(200))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    activo: Mapped[bool] = mapped_column(server_default="true")


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("documento_id", "orden", name="uq_chunks_documento_orden"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index("ix_chunks_metadatos", "metadatos", postgresql_using="gin"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    documento_id: Mapped[int] = mapped_column(ForeignKey("documentos.id", ondelete="CASCADE"))
    orden: Mapped[int] = mapped_column(Integer)
    seccion: Mapped[str] = mapped_column(String(300))
    contenido: Mapped[str] = mapped_column(Text)
    tokens: Mapped[int] = mapped_column(Integer)
    metadatos: Mapped[dict] = mapped_column(JSONB)
    embedding: Mapped[list[float]] = mapped_column(Vector(DIM))
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('spanish', seccion || ' ' || contenido)", persisted=True)
    )
