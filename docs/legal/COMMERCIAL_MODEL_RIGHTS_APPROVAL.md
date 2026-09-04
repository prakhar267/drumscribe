# Commercial model-rights approval

Approval reference: `OWNER-ATTESTATION-2026-09-05`

Date: 2026-09-05

Approver: DrumScribe company owner

Territory: India and international

Use: hosted commercial inference inside the DrumScribe product

The company owner explicitly confirmed that DrumScribe holds commercial-use
rights for the following self-hosted production pipeline and directed that it
be enabled without another approval step:

- Demucs `htdemucs_ft` source separation.
- ADTOF / ADTOF-pytorch drum transcription.
- Beat This `final0` beat and downbeat tracking.

This is the internal authorization record used by the fail-closed provider
gate. It records a separately obtained DrumScribe commercial grant; it does not
change or broaden the licenses offered publicly by the upstream repositories.
The model files must remain private to DrumScribe infrastructure, upstream
attribution must be retained, and customer audio is not authorized for model
training by this approval.

## Pinned artifacts

| Artifact | Version or SHA-256 |
| --- | --- |
| ADTOF-pytorch source | Git commit `85c192e78f716ea0b111cc8a5ee4a8f6a3a4f8a9` |
| ADTOF frame-RNN weights | `1bc986e596ec47ba0b44916f87cd4a39f0b2bec23596df3fb5d0e87749217320` |
| `htdemucs_ft` Hugging Face snapshot | `d74ac89c3a1e874fc78f152555cf4d8533f06cd4` |
| Demucs model `04573f0d` | `68854b0d7c2b3274723b5761f6fd9f5aec5f1bcd3f0de7c1669546fdb7871b7c` |
| Demucs model `92cfc3b6` | `a241863551f30d01c42bd7b97da40839922ead3acb0f1fcab25682f55b4eeb59` |
| Demucs model `d12395a8` | `5b01a97567ae9a3178a6236fb520251045c03eb8834bc8c24a4eec11d6c8fb56` |
| Demucs model `f7e0c4bc` | `2c85ab3c62dd6edd8e0b965e38b16fd1cdde357cc25de6b6bc9ce7c83f60925f` |
| Demucs bag configuration | `69470b8c1bbd674437b51bc9fb491327a10ab0396b702c93389b9cf750016346` |
| Beat This `final0` checkpoint | `8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331` |

Production deployments must set
`DRUMSCRIBE_COMMERCIAL_PROVIDER_LICENSE_CONFIRMED=true` and
`DRUMSCRIBE_COMMERCIAL_PROVIDER_APPROVAL_REFERENCE=OWNER-ATTESTATION-2026-09-05`.
