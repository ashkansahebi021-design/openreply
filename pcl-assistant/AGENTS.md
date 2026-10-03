# PCL assistant maintenance

This directory is an independent Python service. Do not require or migrate the root OpenReply Prisma database to run it.

- Inspect docs/inspection.md before changing deployment architecture.
- Preserve legacy workflow exports; generate current workflows with scripts/build_workflows.py.
- Keep credentials in environment variables or encrypted n8n credentials. No raw errors, headers or tokens in logs.
- Rules before AI; sensitive categories always owner approval. Fail closed when facts, signature, owner identity, comment timestamp or reply window are unknown.
- Do not retry an ambiguous Meta send. Inspect the provider thread before any authorized manual replay.
- Run Python unit tests and scripts/doctor.py for runtime changes; run tests/n8n_smoke.py with N8N_BINARY for workflow changes.
- One process/replica with SQLite on durable local storage. Preserve the n8n encryption key.
- Obtain account-owner OAuth/secrets through secure account settings, never GitHub content.
- A new recurring hosting cost requires a concrete cost-aware owner decision. This task has not selected paid hosting.
