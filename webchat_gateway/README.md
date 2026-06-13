# Webchat Gateway - FastAPI + WebSockets

Esta versión **NO publica mensajes en RabbitMQ**.

El flujo queda así:

```text
Browser Webchat
  ├─ WebSocket: /ws/{sessionId}
  └─ POST /api/messages
          ↓
FastAPI Gateway
          ↓ HTTP POST
n8n Webhook
          ↓
n8n publica en RabbitMQ y procesa con su consumer
          ↓
n8n HTTP Request POST /api/responses
          ↓
FastAPI Gateway
          ↓ WebSocket
Browser Webchat
```

## Arranque

```bash
docker compose -f docker-compose.yml -f docker-compose.webchat.yml --profile dev up -d --build webchat-gateway
```

Abre:

```text
http://localhost:8090
```

## Endpoint usado por el widget

El widget llama a:

```text
POST /api/messages
```

El gateway transforma el mensaje y lo reenvía a:

```text
WEBCHAT_N8N_WEBHOOK_URL
```

## Webhook n8n esperado

En `.env`:

```env
WEBCHAT_N8N_WEBHOOK_URL=http://n8n:5678/webhook/8ddf2e2c-e855-4b8d-a99e-c7d200c6ec57
```

En local, si usas webhook de test, cambia a:

```env
WEBCHAT_N8N_WEBHOOK_URL=http://n8n:5678/webhook-test/8ddf2e2c-e855-4b8d-a99e-c7d200c6ec57
```

## Payload que recibe n8n

```json
{
  "requestId": "req-...",
  "sessionId": "webchat-...",
  "userId": "webchat-...",
  "channel": "webchat",
  "message": "...",
  "chatInput": "...",
  "modelName": "chatgpt",
  "reply": {
    "mode": "websocket",
    "callbackUrl": "http://localhost:8090/api/responses",
    "socketSessionId": "webchat-..."
  },
  "metadata": {
    "source": "webchat-gateway",
    "createdAt": "..."
  }
}
```

## Callback desde n8n al gateway

En la rama final `webchat`, usa un nodo HTTP Request:

```text
POST http://webchat-gateway:8090/api/responses
```

Body JSON:

```json
{
  "requestId": "={{ $json.requestId }}",
  "sessionId": "={{ $json.sessionId }}",
  "userId": "={{ $json.userId }}",
  "channel": "webchat",
  "status": "done",
  "response": "={{ $json.output }}"
}
```

## Importante en n8n

Conserva `requestId` desde el webhook inicial hasta `Enrich Output`.
