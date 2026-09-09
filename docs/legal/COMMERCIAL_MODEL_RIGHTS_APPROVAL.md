# Commercial model-rights owner attestation

Status: **internal authorization record; underlying rights evidence is
incomplete in this repository**

Approval reference: `OWNER-ATTESTATION-2026-09-05`

Date: 2026-09-05

Approver: DrumToScore founder (registered legal identity not recorded here)

Territory: India and international

Intended use: hosted commercial inference inside the DrumToScore product

The founder explicitly confirmed that DrumToScore holds separately obtained
commercial-use rights for the following self-hosted production pipeline and
directed engineering to enable the pinned artifacts:

- Demucs `htdemucs_ft` source separation.
- ADTOF / ADTOF-pytorch drum transcription.
- Beat This `final0` beat and downbeat tracking.

This record is the reference checked by the application configuration gate. It
is evidence of the founder's instruction, but **is not by itself evidence that
an upstream rightsholder granted commercial rights**. It does not change or
broaden the public upstream licenses. Before the first paid transaction, the
company must archive the actual grant/contract or written permission for each
component, including the grantor, recipient legal identity, permitted hosted
use, territory, term, checkpoint coverage, redistribution limits and any
attribution obligations. Legal counsel should confirm that the grant covers the
deployed combination.

Until that evidence is attached to the private company records and reviewed,
engineering approval and legal clearance must not be treated as equivalent.
The model files must remain private to DrumToScore infrastructure, upstream
attribution must be retained, and customer audio is not authorized for model
training by this attestation.

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
Those settings confirm that the deployer selected this internal record; they do
not validate the underlying grant.

## Evidence still required outside the public repository

For each of Demucs/`htdemucs_ft`, ADTOF-pytorch and Beat This `final0`, retain:

- the applicable public license and README snapshot and, where public terms do
  not cover the intended use, the original email, contract or signed permission;
- the rightsholder/grantor and the exact individual or entity receiving rights;
- permission for paid, hosted inference in India and internationally;
- the exact code revision and checkpoint hashes covered by the permission;
- rules for copying weights to cloud servers, backup, modification and
  redistribution;
- attribution, notice, audit, termination and data-use obligations; and
- counsel's approval or a dated risk acceptance by the correctly identified
  business owner.

Do not commit private contracts, email headers, signatures or personal data to
the public GitHub repository. Store them in access-controlled company records
and record only a non-secret evidence identifier here after review.
