from contextlib import asynccontextmanager
import threading

from fastapi import FastAPI

from embedding_worker import run_worker


_worker_thread = None


def _start_worker_once() -> None:
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return

    _worker_thread = threading.Thread(target=run_worker, name="embedding-worker", daemon=True)
    _worker_thread.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the long-running embedding worker in a background daemon thread.
    _start_worker_once()
    yield


app = FastAPI(title="GitChat Embedding Worker Web Service", lifespan=lifespan)


@app.get("/")
def root():
    alive = _worker_thread.is_alive() if _worker_thread else False
    return {
        "service": "embedding-worker-web",
        "worker_running": alive,
    }


@app.get("/health")
def health():
    alive = _worker_thread.is_alive() if _worker_thread else False
    status = "ok" if alive else "degraded"
    return {
        "status": status,
        "worker_running": alive,
    }
