# Commercial drum provider blocker

Status: blocked on external credentials and approval, not on adapter code.

The current Klangio OpenAPI advertises `model=drums` on the transcription endpoint,
but this repository has no account credential or evidence that the target account is
entitled to that model. It also lacks executed commercial terms/DPA, confirmed output
rights, region/subprocessor details, training-use opt-out, deletion SLA and accepted
pricing.

To clear the blocker, provide:

1. `DRUMSCRIBE_KLANGIO_API_KEY` for a non-personal staging workspace with drum-model
   access.
2. `DRUMSCRIBE_KLANGIO_CONTRACT_REFERENCE` and
   `DRUMSCRIBE_COMMERCIAL_PROVIDER_APPROVAL_REFERENCE` tied to reviewed terms/DPA.
3. Written answers for retention/backups, regions, subprocessors, training use,
   deletion, output ownership and support/SLA.
4. A rights-cleared staging corpus with at least two materially different recordings.
5. Approval of the measured transcription quality, correction burden, latency and cost.

Until all five are complete, production startup remains fail-closed and no mock,
research provider or consumer Drum2Notes interface is substituted.
