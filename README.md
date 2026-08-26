# Agent Template

> **This is a GitHub Template Repository.**
> Developers never clone this repo directly. The platform portal creates agent repos from this template via `provision-agent.sh`.
> Every `{{PLACEHOLDER}}` value is replaced automatically during provisioning.
>
> To enable the template feature, go to **Settings → General** and check **Template repository**.

---

## What happens when your agent repo is created

When you request a new agent through the platform portal, `provision-agent.sh` runs and:

1. Creates an Entra service principal (`sp-agent-{name}`)
2. Stores the SP secret in Key Vault
3. Creates an AKS namespace (`agents-{team}`)
4. Creates a ServiceAccount with Workload Identity binding
5. Applies a network policy (deny-all + allow-platform)
6. Registers the APIM route with guardrail pre/post hooks
7. Creates the ACR image path with RBAC
8. Creates a GitHub repo from this template
9. Injects GitHub Actions secrets
10. Replaces all `{{PLACEHOLDER}}` values across every file

---

## Getting started after your repo is created

```bash
git clone <your-agent-repo>
cd <your-agent-repo>
cp .env.example .env
# Fill in .env values (most are pre-populated by provision-agent.sh)

docker compose -f docker-compose.dev.yml up
```

- Agent running at **http://localhost:8000**
- Mock tools running at **http://localhost:8001**
- OTel collector running at **http://localhost:4317**

Test the agent:

```bash
curl -X POST http://localhost:8000/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "model": "my-agent",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

---

## Adding tools to your agent

```bash
# 1. Request tool access via the platform portal
# 2. Once granted, sync the SDK stubs:
agent-sdk sync

# 3. Use in src/agent.py:
from agent_platform_sdk import get_tool

products = get_tool("products-api", context=agent_context)
results = products.list()
```

The SDK handles authentication, header propagation, OTel context, and APIM routing. **Never call backend services directly from agent code.**

---

## File structure

```
agent-template/
├── .github/workflows/
│   ├── ci.yml                  # OPA gate + Promptfoo eval + Docker build
│   └── deploy.yml              # Build + push to ACR + kubectl apply
├── src/
│   ├── agent.py                # LangGraph agent + FastAPI endpoints
│   └── prompts.py              # System prompt loader with caching
├── prompts/
│   └── system.txt              # System prompt (source of truth)
├── evals/
│   ├── promptfooconfig.yaml    # Promptfoo evaluation config
│   └── datasets/
│       └── golden-dataset.json # 5 generic test cases
├── k8s/
│   ├── deployment.yaml         # Kubernetes Deployment
│   ├── service.yaml            # Kubernetes Service (ClusterIP)
│   ├── networkpolicy.yaml      # Deny-all + allow-platform policies
│   └── configmap.yaml          # Agent environment ConfigMap
├── opa/
│   └── agent-policy.rego       # OPA policy for agent.yaml validation
├── dev/
│   ├── mock_tools.py           # Mock tool server for local dev
│   └── otel-collector-config.yaml
├── agent.yaml                  # Agent metadata with placeholders
├── Dockerfile                  # Multi-stage Python 3.12 build
├── docker-compose.dev.yml      # Local dev environment
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variable reference
└── README.md                   # This file
```

---

## CI gate sequence

On every pull request to `main`, three gates must pass — no exceptions:

| Step | Gate | What it checks |
|------|------|---------------|
| 1 | **OPA** | Validates `agent.yaml` — no placeholders remain, `ci_gate=true`, threshold ≥ 0.95 |
| 2 | **Promptfoo** | Runs the eval suite — must pass the configured threshold |
| 3 | **Docker build** | Image builds successfully |

---

## Deploy sequence

On merge to `main`:

| Step | Action |
|------|--------|
| 1 | Azure OIDC login via Workload Identity federation |
| 2 | Build and push Docker image to ACR (`acrshoppoc.azurecr.io`) |
| 3 | Replace placeholders in k8s manifests |
| 4 | `kubectl apply` to the agent's AKS namespace |

---

## API reference

### POST /invoke

OpenAI chat completions compatible endpoint. This is the main entry point for all agent calls routed through APIM.

**Request headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <agent-entra-token>` — validated by APIM |
| `X-User-Token` | No | User token for OBO flows (APIM handles exchange) |
| `X-Session-ID` | No | Session ID — generated if missing |
| `X-Correlation-ID` | No | Correlation ID — injected by APIM |

**Request body:**
```json
{
  "model": "agent-id",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "stream": false
}
```

**Response body:**
```json
{
  "id": "chatcmpl-<uuid>",
  "object": "chat.completion",
  "model": "<agent-id>",
  "choices": [
    {
      "index": 0,
      "message": {"role": "assistant", "content": "..."},
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 20,
    "total_tokens": 30
  }
}
```

**Response headers:** `X-Session-ID`, `X-Correlation-ID`

### POST /evaluate

Internal endpoint called by Promptfoo during CI. Restricted by APIM — not accessible externally.

**Request body:**
```json
{
  "prompt_text": "You are a helpful AI assistant.",
  "prompt_version_label": "v1.0",
  "dataset_id": "golden-dataset",
  "run_label": "ci-run",
  "messages": [{"role": "user", "content": "Hello"}]
}
```

**Response body:**
```json
{
  "run_id": "<uuid>",
  "output": "...",
  "prompt_version": "v1.0",
  "status": "completed"
}
```

### GET /health

No auth required. Used by AKS liveness and readiness probes.

```json
{
  "status": "ok",
  "agent_id": "<agent-id>",
  "prompt_version": "v1.0"
}
```

---

## Environment variables

| Variable | Description | Source |
|----------|-------------|--------|
| `AGENT_ID` | Agent identifier | `provision-agent.sh` |
| `TEAM_NAME` | Team that owns the agent | `provision-agent.sh` |
| `PLATFORM_REGISTRY_URL` | APIM gateway URL (tool registry) | `provision-agent.sh` |
| `KEYVAULT_URL` | Azure Key Vault URI | `provision-agent.sh` |
| `AZURE_CLIENT_ID` | Agent service principal client ID | Workload Identity |
| `AZURE_TENANT_ID` | Entra tenant ID | Workload Identity |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL | ConfigMap |
| `AZURE_OPENAI_DEPLOYMENT` | Azure OpenAI model deployment name | ConfigMap |
| `LANGSMITH_API_KEY` | LangSmith tracing API key (optional) | Key Vault |
| `LANGSMITH_PROJECT` | LangSmith project name (optional) | Key Vault |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OpenTelemetry collector endpoint | ConfigMap |
| `OTEL_SERVICE_NAME` | Service name for OTel traces | ConfigMap |

---

## Placeholder reference

These placeholders are replaced by `provision-agent.sh` when creating a new agent repo:

| Placeholder | Example value | Description |
|-------------|--------------|-------------|
| `{{AGENT_ID}}` | `shopping` | Agent name |
| `{{TEAM_NAME}}` | `retail-eng` | Team name |
| `{{SP_CLIENT_ID}}` | `<uuid>` | Entra SP client ID |
| `{{KEYVAULT_URL}}` | `https://kv-shop-poc.vault.azure.net/` | Key Vault URI |
| `{{INTERACTION_MODEL}}` | `standalone` | `standalone` / `orchestrator` / `sub-agent` |
| `{{GUARDRAIL_PROFILE}}` | `strict` | `strict` / `moderate` / `open` |
| `{{APIM_BASE_URL}}` | `https://apim-shop-poc.azure-api.net` | APIM gateway URL |
| `{{ACR_LOGIN_SERVER}}` | `acrshoppoc.azurecr.io` | ACR login server |
| `{{AZURE_OPENAI_ENDPOINT}}` | `https://oai-shop-poc.openai.azure.com/` | Azure OpenAI endpoint |
| `{{GITHUB_ORG}}` | `my-org` | GitHub organisation name |
