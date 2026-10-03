# Validation report — 2026-10-03

## Passed

- 48 Python tests: normal DM, grounded routine AI mock, keyword comment and wrong-post exclusion, story keyword reply, pricing approval, sensitive-rule bypass prevention, approve/reject/edit/custom actions, owner authorization and message/version checks, duplicate webhook and concurrent duplicate intake, batch fan-out, latest-message/context invalidation, pending handoff, 24-hour/7-day expiry, missing comment time, API rejection, ambiguous send/no replay, 429 backoff, crash recovery, dry-run, pause, budget cap, Persian normalization, byte limit, echo filtering, rule edits, retention/dedup, challenge, signed ingress, internal authentication and secret-free audit.
- Real n8n **2.41.6**, installed from package registry. Imported all five generated workflow graphs and an isolated mock header credential. A/B/C/D/E executed against a local gateway with mock providers. Scheduled/error triggers replaced with manual triggers only in temporary fixtures. Simulated outbound DM confirmed; no Meta/OpenAI/Telegram external call occurred. Production exports remain inactive and retain original schedule/error triggers.
- Gunicorn **23.0.0** serving WSGI `/health` returned HTTP 200.
- Workflow graph connections, inactive defaults, example rule schema, log settings checked by `scripts/doctor.py`.
- Python compile checks and `git diff --check` passed.

## Not yet verified

- Docker image build / Docker Compose launch: Docker is not installed in this execution environment. Python server and actual n8n runtime tested without Docker.
- n8n public API installer against owner instance, scheduled activation, reverse-proxy HTTPS certificate, persistent-host restart/backup restore: no owner instance/host or n8n API key yet. CLI import/execution was tested; installer remains provisioning code requiring commissioning.
- Live Meta webhook, token/scopes/account, App Dashboard access-level/review, real DM/comment/story reply and token renewal: owner authorization needed.
- Live Telegram webhook/card/callback and OpenAI responses: tokens/API key needed. Mock integration covers application behavior, not provider availability or model language quality.
- Existing OpenReply root checks not run; isolated runtime does not import its incomplete Prisma schema or touch its production database. Existing repository-wide CI may still fail for that pre-existing schema issue.

No production migrations, paid hosting deployment, real Instagram responses, or owner Telegram messages were performed.
