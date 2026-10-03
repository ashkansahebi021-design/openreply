# Inspection — 2026-10-03

- Owner repository: ashkansahebi021-design/openreply, inspected at 9d049557fc00a489a0511e116693281f8dd881a4.
- Original Meta adapters already use official Instagram Login graph endpoints, raw-body HMAC, private reply recipient.comment_id, echo filtering and ambiguous-delivery protection. These behaviors are retained in the standalone adapter.
- Three existing PCL n8n workflows recovered and preserved verbatim under workflows/legacy. They are inactive safe-test builds: real ingress and real send deliberately blocked, single-event intake only, placeholder Data Tables, Gemini rather than OpenAI. Their A (receive/draft), B (versioned owner approval), C (send/verify) separation is retained.
- Current prisma/schema.prisma contains only Conversation, references undefined models/enums, and has no generator/datasource. Original upstream schema exists in history. Do not run its migrations or assume this foundation works. This task leaves original source and schema untouched.
- Railway project feisty-passion: one openreply service, failed deployment, no configured service variables or volumes. No connected existing database or live n8n service was found in the inspected project or repository. Other undisclosed hosting accounts were not inspected.
- Local workspace initially empty. No OpenAI/Meta/Telegram/n8n credentials were available (checked names only).

## Decision

Add a separately runnable pcl-assistant directory in the owner fork. Use SQLite on a persistent volume for single-account, low-volume service; no existing database is available to reuse. No OpenReply, Next.js, Redis, Zernio, Supabase or Vercel dependency at runtime. Existing code stays reviewable and unchanged. No production changes or migration applied.
