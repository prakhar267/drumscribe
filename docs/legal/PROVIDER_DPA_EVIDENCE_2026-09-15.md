# Provider DPA and subprocessor evidence — 15 September 2026

This is a non-secret engineering evidence index, not legal advice and not proof
that an account-specific agreement has been accepted. Each SHA-256 is the exact
decompressed HTTP response body retrieved from the provider's official public
URL on 15 September 2026 with a DrumToScore compliance user agent. Public pages
can change; the operator must also retain the accepted dashboard/order version
where the provider offers one.

No payment card, paid plan, customer row, customer object, authentication secret
or private account document was used to build this index.

## Evidence index

| Provider | Official evidence retrieved | HTTP/body evidence | Account-specific status |
| --- | --- | --- | --- |
| Cloudflare | [Customer DPA](https://www.cloudflare.com/cloudflare-customer-dpa/) and [Cloudflare-services subprocessors](https://www.cloudflare.com/gdpr/subprocessors/cloudflare-services/) | Both HTTP 200. DPA: 338,836 bytes, `88d54c3cecdae1c16d0fc7da8d04a25d3035b789c021f945f97a164bc4439690`. Subprocessors: 271,662 bytes, `60c78bdde99b93fa2dd09f758b4405c8db65942ac7c002f1feb0c005a629cc4d` | Retain the self-serve account acceptance/terms record and subscribe to subprocessor changes. |
| Oracle Cloud | [Cloud-services contracts](https://www.oracle.com/contracts/cloud-services/) and [supplier/subprocessor security page](https://www.oracle.com/corporate/security-practices/corporate/supply-chain/suppliers/) | Both HTTP 200. Contracts: 51,073 bytes, `8c0a658aeaf02fbc05e5ca43f85c200d9d9215237f5110ffb762339db0b1d8ec`. Security page: 40,636 bytes, `34420641b1054e5bafd35cb7b95f08f2eb729ca99b74078eae5f0a77c46f6bec` | Export the exact DPA incorporated into this tenancy/order. Oracle distributes the applicable subprocessor list through My Oracle Support, Document ID `2121811.1`; subscribe using `2288528.1`. |
| Modal | [Data Processing Addendum](https://modal.com/legal/dpa) and [subprocessors](https://trust.modal.com/subprocessors) | Both HTTP 200. DPA: 49,380 bytes, `e1debcfe4b6c24013c17821ae88f5026c4f82ece73ca6315598d16ac7552cbe3`. Subprocessors: 6,922 bytes, `0438150d63c32b1f3d41cb268d3ebb68516863f772a8b395c6c1edf7fb2a7f64` | Retain the account acceptance record and written confirmation of the endpoint's deletion/location behavior before relying on it for additional paid territories. |
| Neon / Databricks | [Neon DPA PDF](https://neon.com/pdf/DPA.pdf), [current Neon product schedule](https://neon.com/platform-terms) and [Databricks subprocessors](https://www.databricks.com/legal/databricks-subprocessors) | All HTTP 200. PDF: 1,557,160 bytes, `85839b0fafff55fb83f6acacab131032acbbfc6ff1a0f86e2dde9c0fe1ba8166`. Product schedule: 178,079 bytes, `3e9c6156c7d10e221b7785b70026a9a00ab336595cbf723277b9346bcbf7c6d5`. Subprocessors: 709,153 bytes, `15bdb4b5f229249034fdac57a0b6cb8ca168394c8033e5e221f41070de1a3ef5` | Confirm which Neon/Databricks agreement version governs project `cool-cell-64604736`; retain that accepted copy and the Object Storage beta terms. |
| Resend | [Data Processing Addendum](https://resend.com/legal/dpa) and [subprocessors](https://resend.com/legal/subprocessors) | Both HTTP 200. DPA: 263,139 bytes, `9db481fabe58a5c7952f6e47e55b0b560d5674c1a5a575d7a80f1f73b90329d3`. Subprocessors: 135,427 bytes, `135442627cf8aa7e53ab6ca864ec2870649d1a3b52de47b4aff99a27903c1718` | Download the signed DPA from Resend's account Documents page and enforce/review the 30-day delivery-metadata schedule. |
| Sentry | [Data Processing Addendum](https://sentry.io/legal/dpa/) and [subprocessors](https://sentry.io/legal/subprocessors/) | Both HTTP 200. DPA: 235,791 bytes, `48d5e35509df0da608f2a0de8305e4ec5bcf03cfc6b85fb8b7550933b4cac172`. Subprocessors: 181,678 bytes, `187a17d97de9e97f76545592cad4ca7a94d9f741165881a8bf33da3038c720c2` | Retain the organization-accepted DPA and dashboard evidence for 30-day retention, PII scrubbing and access control. |
| GitHub | [Customer agreements](https://github.com/customer-terms) and [subprocessors](https://docs.github.com/en/site-policy/privacy-policies/github-subprocessors) | Both HTTP 200. Agreements: 308,616 bytes, `e5464ddc9cd3e0b313ed10fd3d21f06d8a89f80cb0fbc155fb0789f8f3ca21c3`. Subprocessors: 146,145 bytes, `b4dd807f12c32a8446bbacdaeef0dcdff1fb04b5563b5928e4bb44e98a9fd18e` | GitHub states its DPA/subprocessor list covers Teams/Enterprise/Copilot products. The present public personal repository is governed by the account terms/privacy statement unless upgraded; uptime checks intentionally contain no customer audio. |
| Dodo Payments | [Data Processing Agreement](https://dodopayments.com/legal/data-processing-agreement) | HTTP 200, 176,233 bytes, `3561c4cfcd83779bb8774f737be4e31e7b9f671d709e98b33759df1d1c4c150a` | The DPA is incorporated into the merchant agreement and describes Dodo as independent controller for merchant-of-record processing. It says the current subprocessor list is available on written request; archive the response from `compliance@dodopayments.com`. |

Private Valkey is not a separate external processor: it runs inside the Oracle
production VM on a private Docker network with append-only persistence and no
published host port. Upstash is no longer a production provider.

## Completion checklist

- [x] Index public DPA/contract and subprocessor evidence for every current
  external production provider.
- [x] Record retrieval date, response status, byte count and SHA-256 without
  committing the retrieved third-party documents or any private account data.
- [ ] Export the exact account-accepted Cloudflare, Oracle, Neon/Databricks,
  Modal, Resend and Sentry agreement versions where available.
- [ ] Retrieve Oracle's tenancy-specific subprocessor list from My Oracle Support.
- [ ] Request and archive Dodo's current subprocessor list in writing.
- [ ] Have qualified counsel approve processor/controller roles, cross-border
  mechanisms and prioritized launch territories.

Recheck this index quarterly and whenever a provider, region, service or material
contract version changes. Record a new dated file rather than rewriting this
historical evidence record.
