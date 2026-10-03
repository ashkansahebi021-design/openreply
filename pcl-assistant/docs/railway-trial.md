# Railway trial commissioning

The owner declined paid ManyChat. Meta developer login remains blocked by a location message. These are independent from the backend implementation.

The gateway built successfully from the PCL branch in the existing Railway project on 2026-10-03. Its HTTPS health endpoint returned HTTP 200. The original main-branch deployment was failing during image build. A 500 MB volume stores gateway SQLite at `/data/pcl.sqlite3`. No paid plan was purchased. Railway volumes mount as root, so this deployment uses the documented `RAILWAY_RUN_UID=0` override. The container default remains non-root for other hosts with suitable volume ownership.

Deploy `Dockerfile.n8n` as a separate single-replica service with a 500 MB `/data` volume and variables `N8N_ENCRYPTION_KEY`, `INTERNAL_API_TOKEN`, `PCL_INTERNAL_URL=http://openreply.railway.internal:8080`, `PORT=5678`, `N8N_PORT=5678`, and `RAILWAY_RUN_UID=0`. **Do not create a public n8n domain**: its unconfigured owner UI must remain private. The bootstrap imports the bearer credential and five graphs, publishes each using the supported CLI, then starts n8n. Workflow, URL or credential changes cause reimport on restart. Unchanged boots retain the graph. Temporary credential files have mode 0600 and are removed; persisted credentials are encrypted by n8n. Both the encryption key and volume are required for restore.

Set gateway `PUBLIC_BASE_URL` to its HTTPS origin. With the separate internal bearer token, POST `/internal/telegram/commission` with `{"expected_username":"<confirmed bot username>"}`. The gateway checks identity with its own Telegram credential, sets the signed webhook without deleting pending updates, and queues one deduplicated owner welcome. No bot token is returned. After n8n is active, send `/status` to verify intake and response. Instagram outbound stays disabled until Meta commissioning. This bot is the owner control channel, not a public ChatGPT chatbot.

Railway trial: one-time $5 credit for up to 30 days, then Free with $1 monthly credit. Restricted trial accounts may not reach external APIs. Neither phase guarantees continuous two-service hosting. Trial volumes may be deleted 30 days after credit expiry; export beforehand. No automatic paid upgrade is authorized.

References: https://docs.railway.com/pricing/free-trial ; https://docs.railway.com/volumes/reference ; https://docs.n8n.io/deploy/host-n8n/configure-n8n/use-the-command-line
