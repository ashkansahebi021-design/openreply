# Validation report — 2026-10-03

## Passed

- 56 Python tests covering DM/comment/story routing, approval/edit/reject/custom reply, owner authentication, signed webhooks, concurrent deduplication, context/version guards, response windows, API rejection and ambiguous delivery, rate-limit retries, dry-run, budget limits, retention, secure Telegram commissioning, idempotent n8n provisioning, and redacted diagnostics.
- Real n8n 2.41.6 CLI imported and executed all five workflow graphs against isolated mock providers. Production schedule/error triggers were preserved.
- Both gateway and n8n Docker images built and deployed successfully in the owner's authorized Railway free trial. Separate persistent volumes are attached. No paid plan was purchased.
- Live gateway HTTPS health returned 200; unsigned Telegram ingress returned 401. Authenticated diagnostics returned 200 without messages or secrets.
- Live n8n startup confirmed five published workflows. Recent heartbeat timestamps confirmed event processing, Telegram processing, outbox dispatch and maintenance schedules actually ran.
- Telegram getMe confirmed the configured bot, signed webhook registration succeeded without dropping pending updates, and the deduplicated owner welcome reached outbox status `sent` after a successful Telegram API response. This does not establish that the owner read it.
- Independent PCL GitHub CI passed for runtime commit 53684b859772df747af5f6ec87c4c8b92b6d545b. Doctor, Python compile checks, JavaScript syntax checks and git diff checks passed.

## Not yet verified

- Owner-originated Telegram `/status`, live approval cards and callback/edit interactions. Application behavior is covered by mocks; owner intake still needs a real message.
- Live Meta authorization, webhook, token/scopes/account, permission review, DM/comment/story response and token renewal. Developer login remains blocked by the location screen. Instagram outbound remains disabled, dry-run enabled and Meta verification false.
- Live OpenAI response quality and connectivity: API key is not configured.
- Full Docker Compose stack, Caddy certificates, persistent-host restore and backup recovery. Railway Docker builds and live schedules were verified separately.
- Existing OpenReply root CI fails; the independent PCL CI passes. The original incomplete Prisma foundation is preserved and no root database migration was performed.

Trial credit and durable-volume retention require follow-up before expiry. No permanent free hosting or paid upgrade is implied by this deployment.
