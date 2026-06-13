import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    import redis.asyncio as redis
except Exception:  # pragma: no cover
    redis = None


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("webchat-gateway")


PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8090")

DEFAULT_N8N_WEBHOOK_URL = os.getenv(
    "N8N_WEBHOOK_URL",
    "http://n8n:5678/webhook/8ddf2e2c-e855-4b8d-a99e-c7d200c6ec57",
)

N8N_WEBHOOK_BASE_URL = os.getenv("N8N_WEBHOOK_BASE_URL", "http://n8n:5678")

N8N_WEBHOOK_TIMEOUT_SECONDS = float(
    os.getenv("N8N_WEBHOOK_TIMEOUT_SECONDS", "15")
)

ALLOWED_N8N_WEBHOOK_URL_PREFIXES = [
    prefix.strip().rstrip("/")
    for prefix in os.getenv(
        "ALLOWED_N8N_WEBHOOK_URL_PREFIXES",
        (
            "http://n8n:5678/webhook,"
            "http://n8n:5678/webhook-test,"
            "http://localhost:5678/webhook,"
            "http://localhost:5678/webhook-test"
        ),
    ).split(",")
    if prefix.strip()
]

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/1")

REDIS_RESPONSE_TTL_SECONDS = int(
    os.getenv("REDIS_RESPONSE_TTL_SECONDS", "600")
)

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:8090,http://localhost:8080,http://localhost:5678",
    ).split(",")
    if origin.strip()
]


app = FastAPI(
    title="Webchat Gateway",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


redis_client = None


class ChatMessageIn(BaseModel):
    message: str = Field(..., min_length=1)
    sessionId: Optional[str] = None
    userId: Optional[str] = None
    requestId: Optional[str] = None
    channel: str = "webchat"
    modelName: Optional[str] = "chatgpt"
    metadata: Dict = Field(default_factory=dict)

    # Dynamic n8n target
    n8nWebhookUrl: Optional[str] = None
    n8nWebhookPath: Optional[str] = None


class ChatMessageQueued(BaseModel):
    type: str = "queued"
    status: str = "queued"
    requestId: str
    sessionId: str
    channel: str = "webchat"
    n8nWebhookUrl: str


class ChatResponseIn(BaseModel):
    requestId: Optional[str] = None
    sessionId: str
    userId: Optional[str] = None

    response: Optional[str] = None
    output: Optional[str] = None
    message: Optional[str] = None

    error: Optional[str] = None
    status: str = "done"
    channel: str = "webchat"
    metadata: Dict = Field(default_factory=dict)

    def response_text(self) -> str:
        return self.response or self.output or self.message or ""


class ConnectionManager:
    def __init__(self) -> None:
        self.active: Dict[str, List[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()

        self.active.setdefault(session_id, []).append(websocket)

        logger.info(
            "WebSocket connected sessionId=%s total=%s",
            session_id,
            len(self.active[session_id]),
        )

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        sockets = self.active.get(session_id, [])

        if websocket in sockets:
            sockets.remove(websocket)

        if not sockets and session_id in self.active:
            del self.active[session_id]

        logger.info("WebSocket disconnected sessionId=%s", session_id)

    async def send_to_session(self, session_id: str, payload: Dict) -> int:
        sockets = list(self.active.get(session_id, []))

        sent = 0
        dead: List[WebSocket] = []

        for websocket in sockets:
            try:
                await websocket.send_json(payload)
                sent += 1
            except Exception:
                dead.append(websocket)

        for websocket in dead:
            await self.disconnect(session_id, websocket)

        return sent


manager = ConnectionManager()


def normalize_webhook_path(path: str) -> str:
    if not path:
        raise HTTPException(
            status_code=400,
            detail="n8nWebhookPath cannot be empty",
        )

    path = path.strip()

    # Accept raw IDs and convert them to /webhook/{id}
    if (
        not path.startswith("/")
        and not path.startswith("http://")
        and not path.startswith("https://")
    ):
        path = f"/webhook/{path}"

    if path.startswith("http://") or path.startswith("https://"):
        return path

    if not path.startswith("/webhook") and not path.startswith("/webhook-test"):
        raise HTTPException(
            status_code=400,
            detail="n8nWebhookPath must start with /webhook or /webhook-test",
        )

    return urljoin(
        N8N_WEBHOOK_BASE_URL.rstrip("/") + "/",
        path.lstrip("/"),
    )


def is_allowed_webhook_url(url: str) -> bool:
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False

    normalized = url.rstrip("/")

    return any(
        normalized.startswith(prefix)
        for prefix in ALLOWED_N8N_WEBHOOK_URL_PREFIXES
    )


def resolve_n8n_webhook_url(payload: ChatMessageIn) -> str:
    if payload.n8nWebhookPath:
        target_url = normalize_webhook_path(payload.n8nWebhookPath)
    elif payload.n8nWebhookUrl:
        target_url = payload.n8nWebhookUrl.strip()
    else:
        target_url = DEFAULT_N8N_WEBHOOK_URL

    if not is_allowed_webhook_url(target_url):
        logger.warning("Rejected dynamic n8n webhook URL: %s", target_url)

        raise HTTPException(
            status_code=400,
            detail="The requested n8n webhook URL is not allowed by this gateway.",
        )

    return target_url


async def cache_response(payload: Dict) -> None:
    if not redis_client:
        return

    request_id = payload.get("requestId")
    session_id = payload.get("sessionId")

    if request_id:
        await redis_client.setex(
            f"webchat:response:request:{request_id}",
            REDIS_RESPONSE_TTL_SECONDS,
            json.dumps(payload, ensure_ascii=False),
        )

    if session_id:
        await redis_client.setex(
            f"webchat:response:session:{session_id}",
            REDIS_RESPONSE_TTL_SECONDS,
            json.dumps(payload, ensure_ascii=False),
        )


async def forward_message_to_n8n(target_url: str, payload: Dict) -> None:

    print()
    print()
    print(target_url)
    print()
    print()
    print()

    async with httpx.AsyncClient(timeout=N8N_WEBHOOK_TIMEOUT_SECONDS) as client:
        response = await client.post(
            target_url,
            json=payload,
        )

    if response.status_code >= 400:
        logger.error(
            "n8n webhook returned error status=%s body=%s",
            response.status_code,
            response.text[:500],
        )

        raise HTTPException(
            status_code=502,
            detail=f"n8n webhook returned {response.status_code}",
        )


async def handle_chat_message(payload: ChatMessageIn) -> ChatMessageQueued:
    session_id = payload.sessionId or f"webchat-{uuid.uuid4()}"
    request_id = payload.requestId or f"req-{uuid.uuid4()}"
    user_id = payload.userId or session_id
    target_url = resolve_n8n_webhook_url(payload)

    webhook_payload = {
        "requestId": request_id,
        "sessionId": session_id,
        "userId": user_id,
        "channel": payload.channel or "webchat",
        "message": payload.message,
        "chatInput": payload.message,
        "modelName": payload.modelName or "chatgpt",
        "reply": {
            "mode": "websocket",
            "callbackUrl": f"{PUBLIC_BASE_URL.rstrip('/')}/api/responses",
            "socketSessionId": session_id,
        },
        "metadata": {
            **payload.metadata,
            "source": "webchat-gateway",
            "transport": "websocket",
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "n8nWebhookTarget": target_url,
        },
    }

    await forward_message_to_n8n(
        target_url=target_url,
        payload=webhook_payload,
    )

    queued = ChatMessageQueued(
        requestId=request_id,
        sessionId=session_id,
        channel="webchat",
        n8nWebhookUrl=target_url,
    )

    await manager.send_to_session(
        session_id,
        queued.model_dump(),
    )

    return queued


@app.on_event("startup")
async def on_startup() -> None:
    global redis_client

    if redis is not None and REDIS_URL:
        try:
            redis_client = redis.from_url(
                REDIS_URL,
                decode_responses=True,
            )

            await redis_client.ping()

            logger.info("Redis connected")
        except Exception as exc:
            redis_client = None

            logger.warning(
                "Redis unavailable, continuing without response cache: %s",
                exc,
            )

    logger.info("Default n8n webhook URL: %s", DEFAULT_N8N_WEBHOOK_URL)
    logger.info(
        "Allowed n8n webhook URL prefixes: %s",
        ALLOWED_N8N_WEBHOOK_URL_PREFIXES,
    )


@app.on_event("shutdown")
async def on_shutdown() -> None:
    if redis_client:
        await redis_client.close()


@app.get("/health")
async def health() -> Dict:
    return {
        "status": "ok",
        "service": "webchat-gateway",
        "version": "2.0.0",
        "time": datetime.now(timezone.utc).isoformat(),
        "defaultN8nWebhookUrl": DEFAULT_N8N_WEBHOOK_URL,
        "allowedN8nWebhookUrlPrefixes": ALLOWED_N8N_WEBHOOK_URL_PREFIXES,
    }


@app.get("/")
async def index() -> FileResponse:
    return FileResponse("app/static/index.html")


@app.post("/api/messages", response_model=ChatMessageQueued)
async def create_message(payload: ChatMessageIn) -> ChatMessageQueued:
    """
    HTTP fallback.

    The preferred flow is WebSocket:
    front -> /ws/{sessionId} -> gateway -> n8n webhook.
    """
    try:
        return await handle_chat_message(payload)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to forward message to n8n")

        raise HTTPException(
            status_code=503,
            detail=f"Unable to forward message to n8n: {exc}",
        )


@app.post("/api/responses")
async def receive_response(payload: ChatResponseIn) -> Dict:
    text = payload.response_text()

    event = {
        "type": "chat.response"
        if payload.status != "error" and not payload.error
        else "chat.error",
        "status": payload.status,
        "requestId": payload.requestId,
        "sessionId": payload.sessionId,
        "userId": payload.userId,
        "channel": payload.channel,
        "response": text,
        "error": payload.error,
        "metadata": payload.metadata,
        "receivedAt": datetime.now(timezone.utc).isoformat(),
    }

    sent = await manager.send_to_session(
        payload.sessionId,
        event,
    )

    if sent == 0:
        await cache_response(event)

    return {
        "status": "delivered" if sent else "cached",
        "sent": sent,
        "sessionId": payload.sessionId,
        "requestId": payload.requestId,
    }


@app.get("/api/responses/{request_id}")
async def get_cached_response(request_id: str) -> Dict:
    if not redis_client:
        raise HTTPException(
            status_code=404,
            detail="Response cache is disabled or unavailable",
        )

    raw = await redis_client.get(
        f"webchat:response:request:{request_id}"
    )

    if not raw:
        raise HTTPException(
            status_code=404,
            detail="Response not found",
        )

    return json.loads(raw)


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
) -> None:
    await manager.connect(session_id, websocket)

    await websocket.send_json(
        {
            "type": "connected",
            "sessionId": session_id,
            "status": "ok",
            "time": datetime.now(timezone.utc).isoformat(),
        }
    )

    try:
        while True:
            data = await websocket.receive_text()

            try:
                raw_payload = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "type": "chat.error",
                        "error": "Invalid JSON message",
                    }
                )
                continue

            message_type = raw_payload.get("type")

            if message_type == "ping":
                await websocket.send_json(
                    {
                        "type": "pong",
                        "time": datetime.now(timezone.utc).isoformat(),
                    }
                )
                continue

            if message_type != "chat.message":
                await websocket.send_json(
                    {
                        "type": "chat.error",
                        "error": f"Unsupported message type: {message_type}",
                    }
                )
                continue

            try:
                payload = ChatMessageIn(
                    message=raw_payload.get("message", ""),
                    sessionId=raw_payload.get("sessionId") or session_id,
                    userId=raw_payload.get("userId") or session_id,
                    requestId=raw_payload.get("requestId"),
                    channel=raw_payload.get("channel") or "webchat",
                    modelName=raw_payload.get("modelName") or "chatgpt",
                    metadata=raw_payload.get("metadata") or {},
                    n8nWebhookUrl=raw_payload.get("n8nWebhookUrl"),
                    n8nWebhookPath=raw_payload.get("n8nWebhookPath"),
                )

                await handle_chat_message(payload)

            except HTTPException as exc:
                await websocket.send_json(
                    {
                        "type": "chat.error",
                        "requestId": raw_payload.get("requestId"),
                        "sessionId": session_id,
                        "error": exc.detail,
                        "statusCode": exc.status_code,
                    }
                )

            except Exception as exc:
                logger.exception("Failed handling WebSocket chat.message")

                await websocket.send_json(
                    {
                        "type": "chat.error",
                        "requestId": raw_payload.get("requestId"),
                        "sessionId": session_id,
                        "error": str(exc),
                        "statusCode": 503,
                    }
                )

    except WebSocketDisconnect:
        await manager.disconnect(session_id, websocket)

    except Exception:
        logger.exception("WebSocket error sessionId=%s", session_id)

        await manager.disconnect(session_id, websocket)


app.mount(
    "/static",
    StaticFiles(directory="app/static"),
    name="static",
)