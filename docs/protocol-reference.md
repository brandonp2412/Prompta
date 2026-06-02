# ChatGPT Web Protocol Reference — Autonomous Discovery

Autonomously captured: 2026-06-02 via CDP Runtime.evaluate + Bearer token auth
Account: ChatGPT Plus (user@example.com)
Success: 21/28 endpoints

## Authentication

### Access Token
```
GET /api/auth/session  →  {accessToken: "eyJ...", user: {...}, expires: "..."}
```
- JWT token, ~1983 chars
- All `/backend-api/` calls need: `Authorization: Bearer <token>`
- Token has expiry; refresh via same endpoint
- `credentials: 'include'` needed for cookies (Cloudflare, session)

### 403 "Unusual activity" Block
- POST endpoints (`/f/conversation`) return 403 when called from `Runtime.evaluate`
- Requires valid sentinel token (Turnstile + PoW + so challenge)
- Must go through the full sentinel flow first: prepare → solve PoW → solve Turnstile → finalize
- This is the main blocker for autonomous message sending

## Model Catalog

| Slug | Title | Max Tokens | Reasoning | Tools |
|------|-------|-----------|-----------|-------|
| `gpt-5-5` | GPT-5.5 | 34,834 | auto | tools, tools2, dalle_3, search, canvas |
| `gpt-5-3` | GPT-5.3 | 34,834 | auto | tools, tools2, dalle_3, search, canvas |
| `gpt-5-2` | GPT-5.2 | 25,384 | auto | tools, tools2, dalle_3, search, canvas |
| `gpt-5-1` | GPT-5.1 | 17,384 | auto | tools, tools2, dalle_3, search, canvas |
| `gpt-5` | GPT-5 | 16,384 | auto | tools, tools2, dalle_3, search, canvas |
| `gpt-5-3-mini` | GPT-5.3 Mini | 34,834 | none | tools, tools2, dalle_3, search, canvas |
| `gpt-5-mini` | GPT-5-mini | 8,191 | none | tools, tools2, dalle_3, search, canvas |
| `auto` | Auto | 16,384 | auto | tools, tools2, dalle_3, search, canvas |

Default: `auto`, Latest version: `5.5`

## Endpoints (Captured + Working)

### Auth & User
| Endpoint | Status | Response Size | Notes |
|----------|--------|--------------|-------|
| `GET /api/auth/session` | 200 | ~2KB | Access token + user info |
| `GET /backend-api/me` | 200 | ~1KB | User profile (id, name, email, country) |
| `GET /backend-api/accounts/check/v4-2023-04-27` | 200 | ~8KB | Account status, plan_type=plus |
| `GET /backend-api/settings/user` | 200 | ~6KB | User settings, announcements, preferences |
| `GET /backend-api/user_segments` | 200 | ~35B | Feature flags |
| `GET /backend-api/user_system_messages` | 200 | — | System messages |
| `GET /backend-api/user_granular_consent` | 200 | — | Consent state |

### Models
| Endpoint | Status | Response Size | Notes |
|----------|--------|--------------|-------|
| `GET /backend-api/models` | 200 | ~46KB | Full model catalog |
| `GET /backend-api/models/gpts` | 200 | ~336B | GPT-specific models |

### Conversations
| Endpoint | Status | Response Size | Notes |
|----------|--------|--------------|-------|
| `GET /backend-api/conversations?offset=0&limit=28&order=updated` | 200 | ~4KB | Conversation list |
| `GET /backend-api/conversation/{id}` | 200 | ~9KB | Full conversation with message mapping |
| `POST /backend-api/conversation/init` | 200 | ~654B | Returns limits, default model |
| `GET /backend-api/conversation/{id}/stream_status` | 200 | — | Stream status |
| `GET /backend-api/pins` | 200 | ~2B | Pinned conversations |
| `GET /backend-api/calpico/chatgpt/rooms/summary` | 200 | ~57B | Rooms summary |

### Projects (Gizmos)
| Endpoint | Status | Response Size | Notes |
|----------|--------|--------------|-------|
| `GET /backend-api/gizmos/snorlax/sidebar` | 200 | ~162KB | All projects + GPTs |
| `GET /backend-api/gizmos/{id}` | 200 | varies | Full project detail |

#### Project Structure (gizmo detail)
```json
{
  "gizmo": {
    "id": "g-p-6a1e3f6804588191902b398f5afcd6a7",
    "short_url": "g-p-6a1e3f6804588191902b398f5afcd6a7-c-project-shared",
    "gizmo_type": "snorlax",
    "display": {"name": "C-project-shared", "description": ""},
    "memory_scope": "global",         // "global" = shared, "project_v2" = dedicated
    "memory_enabled": true,
    "instructions": "",
    "context_stuffing_budget": 49152,
    "voice": {"id": "ember"},
    "tools": [],
    "files": [],
    "current_user_permission": {"can_delete": true, "can_write": true, ...}
  }
}
```

**Memory scopes captured:**
- `global` — shared memory (uses global ChatGPT memory)
- `project_v2` — dedicated memory (project-specific)
- `global_enabled` — on conversation level (inherited from project)

### Images & Tasks
| Endpoint | Status | Response Size | Notes |
|----------|--------|--------------|-------|
| `GET /backend-api/images/bootstrap` | 200 | ~288B | Image count, thumbnail |
| `GET /backend-api/tasks` | 200 | ~62KB | Background tasks (image gen, research) |

#### Task Structure
```json
{
  "task_id": "imagegen_6a1e7295...",
  "title": "Close-up of a black insect on gravel",
  "status": "completed",
  "conversation_id": "...",
  "created_at": "2026-06-02T06:05:09+00:00"
}
```

### Sentinel (Anti-Abuse)
| Endpoint | Status | Notes |
|----------|--------|-------|
| `POST /backend-api/sentinel/chat-requirements/prepare` | 200 | Returns challenges |
| `POST /backend-api/sentinel/chat-requirements/finalize` | ? | Submit solutions |

#### Sentinel Prepare Response
```json
{
  "persona": "chatgpt-noauth",
  "prepare_token": "gAAAAABq...",
  "turnstile": {
    "required": true,
    "dx": "P2MJGxlSAkga..."   // encrypted Turnstile challenge
  },
  "proofofwork": {
    "required": true,
    "seed": "0.014308608738510697",
    "difficulty": "069ae0"
  },
  "so": {
    "required": true,
    "collector_dx": "P2MJGxlXBEg..."   // encrypted so challenge
  }
}
```

### Connectors
| Endpoint | Status | Notes |
|----------|--------|-------|
| `GET /backend-api/aip/connectors/list_accessible` | 404 | May need different params |
| `GET /backend-api/system_hints?mode=basic` | 200 | System capabilities (search) |
| `GET /backend-api/system_hints?mode=connectors` | 200 | Deep Research, GitHub, OpenAI Platform |
| `GET /backend-api/apps/sources_dropdown` | 200 | ~291KB! Full GPT marketplace catalog |

### Chat (BLOCKED by sentinel)
| Endpoint | Status | Notes |
|----------|--------|-------|
| `POST /backend-api/f/conversation` | **403** | Needs valid sentinel token |
| `POST /backend-api/f/conversation/prepare` | ? | Predictive pre-flight |

## Conversation Detail Structure

```json
{
  "title": "Jet Black Paint Change",
  "conversation_id": "6a1e7275-...",
  "gizmo_id": "g-fTA4FQ7wj",
  "gizmo_type": "gpt",
  "default_model_slug": "gpt-5-5",
  "memory_scope": "global_enabled",
  "is_temporary_chat": false,
  "is_do_not_remember": false,
  "current_node": "28990604-...",
  "mapping": {
    "<uuid>": {
      "id": "<uuid>",
      "message": {
        "id": "<uuid>",
        "author": {"role": "user|assistant|system|tool"},
        "content": {
          "content_type": "text|multimodal_text|code|model_editable_context",
          "parts": ["..."]
        },
        "status": "finished_successfully",
        "metadata": {}
      },
      "parent": "<parent_uuid>",
      "children": ["<child_uuid>"]
    }
  }
}
```

## User Info Captured
```json
{
  "id": "ua-87c65f22-31e2-4f62-970f-05e4bd43da81",
  "name": "Nabeel Alajmah",
  "email": "user@example.com",
  "country": "SA",
  "region": "Mecca Region",
  "plan_type": "plus",
  "subscription_plan": "chatgptplusplan"
}
```

## Key Findings

1. **Auth**: JWT Bearer token from `/api/auth/session` — required for all `/backend-api/` calls
2. **Sentinel is the gatekeeper**: 3 challenges required per message (Turnstile, PoW, so)
3. **PoW**: seed + difficulty pattern captured; algorithm still unknown (hash-wasm based)
4. **Turnstile**: encrypted `dx` blob — must be solved in-browser context
5. **Projects ARE gizmos**: `gizmo_type: "snorlax"`, memory_scope differentiates shared vs dedicated
6. **Message mapping is a tree**: each node has parent + children, supporting branching conversations
7. **193 images** generated, **28 background tasks** active on this account
8. **~162KB** of project/GPT catalog from sidebar endpoint
9. **Conversation init** returns rate limits (file_upload: 3, paste_text_to_file: 3, dictation: 1)
