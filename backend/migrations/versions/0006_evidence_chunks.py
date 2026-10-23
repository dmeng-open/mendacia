"""create evidence_chunks, the searchable index of case documents"""

from alembic import op

from app.config import Settings

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        f"""
        create table evidence_chunks (
            case_version text not null,
            document_id text not null,
            ordinal integer not null,
            case_id text not null,
            title text not null,
            source text not null,
            unlocked_by text[] not null default '{{}}',
            text text not null,
            embedding vector({Settings().embed_dim}) not null,
            text_sha text not null,
            tsv tsvector generated always as (
                setweight(to_tsvector('english', title), 'A')
                || setweight(to_tsvector('english', text), 'B')
            ) stored,
            created_at timestamptz not null default now(),
            primary key (case_version, document_id, ordinal)
        )
        """
    )
    op.execute("create index evidence_chunks_tsv on evidence_chunks using gin (tsv)")


def downgrade() -> None:
    op.drop_table("evidence_chunks")
