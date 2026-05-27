"""Entity extraction from parsed documents using Anthropic tool calling."""
import os
from uuid import UUID

import psycopg
from anthropic import Anthropic
from pydantic import BaseModel

from ingestion.elements import ParsedDoc

_MAX_TOKENS = 100_000
_TIKTOKEN_APPROX_RATIO = 0.75  # rough chars-per-token for truncation guard


class HarnessComponent(BaseModel):
    name: str
    category: str
    purpose: str
    description: str
    introduced_by: str | None = None
    source_doc_id: str


class FailureMode(BaseModel):
    name: str
    category: str
    description: str
    source_doc_id: str


class Harness(BaseModel):
    name: str
    organization: str | None = None
    notable_features: list[str]


class BenchmarkResult(BaseModel):
    benchmark: str
    model: str
    harness_name: str
    rank: int | None = None
    score: float | None = None
    source_doc_id: str


class Practitioner(BaseModel):
    name: str
    affiliation: str | None = None
    contributed_concept: str | None = None
    source_doc_id: str


class ExtractionResult(BaseModel):
    components: list[HarnessComponent]
    failures: list[FailureMode]
    harnesses: list[Harness]
    benchmarks: list[BenchmarkResult]
    practitioners: list[Practitioner]
    component_failure_links: list[tuple[str, str]]


_TOOL_SCHEMA = {
    "name": "store_entities",
    "description": "Store all extracted entities from the document.",
    "input_schema": {
        "type": "object",
        "properties": {
            "components": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "category": {
                            "type": "string",
                            "enum": ["context", "execution", "persistence", "observability",
                                     "orchestration", "safety", "memory", "verification"],
                        },
                        "purpose": {"type": "string"},
                        "description": {"type": "string"},
                        "introduced_by": {"type": "string"},
                        "source_doc_id": {"type": "string"},
                    },
                    "required": ["name", "category", "purpose", "description", "source_doc_id"],
                },
            },
            "failures": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "category": {
                            "type": "string",
                            "enum": ["long-horizon", "safety", "quality", "context", "cost", "retrieval"],
                        },
                        "description": {"type": "string"},
                        "source_doc_id": {"type": "string"},
                    },
                    "required": ["name", "category", "description", "source_doc_id"],
                },
            },
            "harnesses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "organization": {"type": "string"},
                        "notable_features": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name", "notable_features"],
                },
            },
            "benchmarks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "benchmark": {"type": "string"},
                        "model": {"type": "string"},
                        "harness_name": {"type": "string"},
                        "rank": {"type": "integer"},
                        "score": {"type": "number"},
                        "source_doc_id": {"type": "string"},
                    },
                    "required": ["benchmark", "model", "harness_name", "source_doc_id"],
                },
            },
            "practitioners": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "affiliation": {"type": "string"},
                        "contributed_concept": {"type": "string"},
                        "source_doc_id": {"type": "string"},
                    },
                    "required": ["name", "source_doc_id"],
                },
            },
            "component_failure_links": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "description": "Pairs of [component_name, failure_name] that are linked.",
            },
        },
        "required": ["components", "failures", "harnesses", "benchmarks", "practitioners", "component_failure_links"],
    },
}

_SYSTEM = """\
You are a precise information-extraction engine for harness engineering documents.
Extract only entities EXPLICITLY mentioned in the document.
Do not invent, generalize, or infer. If unsure, omit.
Every entity you extract must include the source_doc_id provided in the user message.

component category MUST be one of: context, execution, persistence, observability, orchestration, safety, memory, verification.
failure_mode category MUST be one of: long-horizon, safety, quality, context, cost, retrieval.

EXTRACTION RULES:
- A "harness component" is a NAMED, REUSABLE pattern or primitive (e.g. "AGENTS.md", "Ralph Loop", "context firewall", "hooks", "compaction", "sub-agents"). Generic concepts ("good design", "iteration", "feedback") are NOT components.
- A "failure mode" is a SPECIFIC, NAMED problem (e.g. "context rot", "early stopping", "hallucinated SQL"). Vague issues ("things go wrong", "quality drops") are NOT failure modes.
- Component and failure names must be 1-4 words. Reject anything longer.
- If a candidate appears only once in the document and is not capitalized or quoted, do not extract it.
- When in doubt, omit. Quality over recall.\
"""


_ING_PREFIXES = (
    "using", "building", "creating", "making", "adding", "running",
    "handling", "managing", "processing", "implementing", "providing",
    "allowing", "enabling", "supporting", "ensuring", "avoiding",
)


def _filter_entities(items: list, name_attr: str = "name") -> list:
    """Drop extracted entities whose name is > 50 chars or starts with an -ing verb."""
    kept = []
    for item in items:
        name: str = getattr(item, name_attr, "")
        if len(name) > 50:
            continue
        first_word = name.split()[0].lower() if name.split() else ""
        if first_word in _ING_PREFIXES:
            continue
        kept.append(item)
    return kept


def extract_entities(doc_id: UUID, parsed: ParsedDoc) -> ExtractionResult:
    doc_id_str = str(doc_id)
    client = Anthropic()
    model = os.environ.get("WORKER_MODEL", "claude-haiku-4-5")

    # Build full document text from text, heading, and table/figure content
    text_parts = [
        e.content
        for e in parsed.elements
        if e.element_type in ("text", "heading", "table", "figure")
    ]
    full_text = "\n".join(text_parts)

    # Truncate at ~100k tokens (rough char estimate)
    max_chars = int(_MAX_TOKENS * (1 / _TIKTOKEN_APPROX_RATIO))
    if len(full_text) > max_chars:
        print(f"  WARNING: document truncated from {len(full_text)} to {max_chars} chars for entity extraction")
        full_text = full_text[:max_chars]

    user_msg = (
        f"source_doc_id: {doc_id_str}\n\n"
        f"Document title: {parsed.title}\n\n"
        f"{full_text}"
    )

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=_SYSTEM,
        tools=[_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "store_entities"},
        messages=[{"role": "user", "content": user_msg}],
    )

    # Extract the tool call result
    tool_input: dict = {}
    for block in response.content:
        if block.type == "tool_use" and block.name == "store_entities":
            tool_input = block.input
            break

    def _safe_list(cls, key: str) -> list:
        return [cls(**item) for item in tool_input.get(key, []) if isinstance(item, dict)]

    components = _filter_entities(_safe_list(HarnessComponent, "components"))
    failures = _filter_entities(_safe_list(FailureMode, "failures"))
    harnesses = _safe_list(Harness, "harnesses")
    benchmarks = _safe_list(BenchmarkResult, "benchmarks")
    practitioners = _safe_list(Practitioner, "practitioners")
    links = [
        tuple(lnk)
        for lnk in tool_input.get("component_failure_links", [])
        if isinstance(lnk, (list, tuple)) and len(lnk) == 2
    ]

    return ExtractionResult(
        components=components,
        failures=failures,
        harnesses=harnesses,
        benchmarks=benchmarks,
        practitioners=practitioners,
        component_failure_links=links,
    )


_VALID_COMPONENT_CATEGORIES = frozenset(
    ["context", "execution", "persistence", "observability", "orchestration", "safety", "memory", "verification"]
)
_VALID_FAILURE_CATEGORIES = frozenset(
    ["long-horizon", "safety", "quality", "context", "cost", "retrieval"]
)


def upsert_entities(result: ExtractionResult) -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        # -- harness_components --
        comp_name_to_id: dict[str, int] = {}
        for c in result.components:
            if c.category not in _VALID_COMPONENT_CATEGORIES:
                print(f"  SKIP component '{c.name}': invalid category '{c.category}'")
                continue
            row = conn.execute(
                """
                INSERT INTO harness_components (name, category, purpose, description, introduced_by, source_doc_id)
                VALUES (%s, %s, %s, %s, %s, %s::uuid)
                ON CONFLICT (name) DO UPDATE
                  SET category = EXCLUDED.category,
                      purpose = EXCLUDED.purpose,
                      description = EXCLUDED.description,
                      introduced_by = EXCLUDED.introduced_by
                RETURNING component_id
                """,
                (c.name, c.category, c.purpose, c.description, c.introduced_by, c.source_doc_id),
            ).fetchone()
            if row:
                comp_name_to_id[c.name] = row[0]

        # -- failure_modes --
        failure_name_to_id: dict[str, int] = {}
        for f in result.failures:
            if f.category not in _VALID_FAILURE_CATEGORIES:
                print(f"  SKIP failure '{f.name}': invalid category '{f.category}'")
                continue
            row = conn.execute(
                """
                INSERT INTO failure_modes (name, category, description, source_doc_id)
                VALUES (%s, %s, %s, %s::uuid)
                ON CONFLICT (name) DO UPDATE
                  SET category = EXCLUDED.category,
                      description = EXCLUDED.description
                RETURNING failure_id
                """,
                (f.name, f.category, f.description, f.source_doc_id),
            ).fetchone()
            if row:
                failure_name_to_id[f.name] = row[0]

        # -- harnesses --
        harness_name_to_id: dict[str, int] = {}
        for h in result.harnesses:
            features = h.notable_features  # list[str] -> array
            row = conn.execute(
                """
                INSERT INTO harnesses (name, organization, notable_features)
                VALUES (%s, %s, %s)
                ON CONFLICT (name) DO UPDATE
                  SET organization = EXCLUDED.organization,
                      notable_features = EXCLUDED.notable_features
                RETURNING harness_id
                """,
                (h.name, h.organization, features),
            ).fetchone()
            if row:
                harness_name_to_id[h.name] = row[0]

        # -- benchmark_results --
        for b in result.benchmarks:
            harness_id = harness_name_to_id.get(b.harness_name)
            conn.execute(
                """
                INSERT INTO benchmark_results (benchmark, model, harness_id, rank, score, source_doc_id)
                VALUES (%s, %s, %s, %s, %s, %s::uuid)
                ON CONFLICT DO NOTHING
                """,
                (b.benchmark, b.model, harness_id, b.rank, b.score, b.source_doc_id),
            )

        # -- practitioners --
        for p in result.practitioners:
            conn.execute(
                """
                INSERT INTO practitioners (name, affiliation, contributed_concept, source_doc_id)
                VALUES (%s, %s, %s, %s::uuid)
                ON CONFLICT (name) DO UPDATE
                  SET affiliation = EXCLUDED.affiliation,
                      contributed_concept = EXCLUDED.contributed_concept
                """,
                (p.name, p.affiliation, p.contributed_concept, p.source_doc_id),
            )

        # -- component_failure links --
        for comp_name, failure_name in result.component_failure_links:
            cid = comp_name_to_id.get(comp_name)
            fid = failure_name_to_id.get(failure_name)
            if cid and fid:
                conn.execute(
                    """
                    INSERT INTO component_addresses_failure (component_id, failure_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (cid, fid),
                )

        conn.commit()
