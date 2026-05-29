# syntax=docker/dockerfile:1.7
#
# Backend image for Railway (long-lived uvicorn process, not Lambda — see
# docs/adr/004-railway-over-lambda.md). Multi-stage: a uv builder resolves the
# environment from the committed uv.lock, and a distroless runtime ships only
# CPython + the resolved site-packages (no shell, no package manager, no build
# toolchain) for a small image and minimal attack/cold-start surface.

############################
# Stage 1 — builder
############################
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

# Bytecode-compile on install (faster first request), copy rather than symlink
# so the venv is self-contained and relocatable into the distroless stage, and
# never fetch a managed Python — we want the image's 3.11 ABI.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# 1) Dependency layer — cached on (pyproject.toml + uv.lock) ONLY. Bind mounts
#    keep the manifests out of the image layers; the cache mount preserves uv's
#    wheel/download cache across builds. Source edits do not bust this layer.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-default-groups --no-install-project

# 2) Project layer — rebuilds only when source changes. --no-editable bakes the
#    app/ingestion/evals packages into site-packages so the runtime stage needs
#    nothing but the venv. (hatch wheel targets require all three to be present.)
COPY pyproject.toml uv.lock ./
COPY app ./app
COPY ingestion ./ingestion
COPY evals ./evals
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-default-groups --no-editable

############################
# Stage 2 — runtime (distroless: no shell, no pkg manager, nonroot)
############################
FROM gcr.io/distroless/python3-debian12:nonroot

WORKDIR /app

# Copy ONLY the resolved environment. distroless python3-debian12 ships CPython
# 3.11, matching the builder ABI, so the compiled wheels import as-is.
COPY --from=builder /app/.venv/lib/python3.11/site-packages /app/site-packages
COPY serve.py /app/serve.py

ENV PYTHONPATH=/app/site-packages \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

EXPOSE 8000

# distroless ENTRYPOINT is python3; serve.py reads $PORT (no shell to expand it).
CMD ["/app/serve.py"]
