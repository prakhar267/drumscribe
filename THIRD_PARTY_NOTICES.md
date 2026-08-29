# Third-party dependency register

Last reviewed: 2026-08-29. This engineering register is not legal advice. Exact
versions and integrity hashes are pinned in `pnpm-lock.yaml` and the three
`uv.lock` files; CI audits every release graph and blocks high-severity findings.

| Runtime component | Declared license | Use and release obligation |
|---|---|---|
| Next.js / React | MIT | Preserve upstream copyright and license notices in distributions. |
| Lucide | ISC | Preserve the ISC notice. |
| Verovio 6.3.0 | LGPL-3.0-or-later | Loaded as an unmodified, separately identifiable WASM/JS library. Preserve its license and notices, publish any Verovio modifications, and retain the user's ability to replace/relink the library in distributed builds. |
| FastAPI / Uvicorn | MIT / BSD-3-Clause | Preserve notices. |
| SQLAlchemy / Alembic | MIT | Preserve notices. |
| Celery | BSD-3-Clause | Preserve notices. |
| boto3 / botocore | Apache-2.0 | Preserve the Apache license, NOTICE material, and modification notices. |
| PostgreSQL | PostgreSQL License | Managed service or separate container; preserve notices when redistributed. |
| Valkey | BSD-3-Clause | Separate service container; preserve notices. |
| MinIO server/client | AGPL-3.0 | Used only as the local-development object-store emulator here. Do not redistribute a modified hosted MinIO build without completing an AGPL review and source-offer obligations. Production may use a managed S3-compatible service instead. |
| FFmpeg / FFprobe | Build-dependent LGPL/GPL | Runtime executable only. Record the exact production build configuration and included codecs; ship the corresponding notices/source offer required by that build. |
| ReportLab | BSD | Optional PDF implementation; preserve notices. |
| NumPy / SciPy / librosa / soundfile | BSD/ISC family, dependency-specific | Optional research/audio extras only; preserve their complete transitive notices when shipped. |

Model, checkpoint, and dataset rights are governed separately in
`MODEL_LICENSING.md`; a library's code license never authorizes a model or its
training data. Demucs and every unresolved/non-commercial research provider stay
outside production images and are rejected by the production configuration gate.

Before a public release, generate an SBOM from the locked dependency graphs,
archive all corresponding license texts with the release artifact, and have
counsel review LGPL/AGPL/FFmpeg distribution details plus the legal-page copy.
