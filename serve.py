"""Container entrypoint.

The distroless runtime image has no shell, so Railway's $PORT cannot be expanded
in an exec-form CMD. Read it here and hand off to uvicorn in-process — this also
makes uvicorn PID 1, so it receives SIGTERM directly for graceful shutdown.
"""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.api.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        # Single worker: the pipeline is async/IO-bound (LLM + DB + Redis), and
        # Railway scales horizontally across containers rather than in-process.
        workers=1,
    )
