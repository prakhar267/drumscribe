# Product decisions

## First release

- The product sells correction speed, not impossible certainty. Quality summaries say where review is useful and low-confidence notes are easy to traverse.
- Upload precedes account creation. Anonymous ownership is session-bound and transferable after sign-in.
- The editor is desktop-first; tablet supports editing, while narrow screens prioritize playback and practice.
- The drum grid is the fastest precision editor and professional notation is a synchronized projection of the same canonical events.
- Original onset and quantized position coexist. Playback follows expressive source timing; notation remains readable.
- The authoritative audio clock lives in one transport store. Visuals subscribe; none creates an independent timer.
- `FREE_BETA` is the only initial entitlement. Quota and flag interfaces exist, but no billing UI or payment provider is included.
- Projects are private. There is no public gallery, streaming-service importer, or automatic publication of generated charts.

## Model strategy

The always-available development path is deterministic and useful for exercising the product. A research provider may run locally for benchmarking, but startup blocks it in production until every licensing field is approved. Separation and transcription can be replaced independently. This keeps a future proprietary model or licensed API from leaking into product-domain code.

## Graceful limits

Rock, pop, indie, alternative, and straightforward contemporary arrangements are the honest initial scope. Triplets and variable tempo are feature-flagged. Uncertain meter defaults conservatively to 4/4 and remains user-correctable. Dense/irregular material receives a review warning instead of an unsupported accuracy claim.

## Privacy posture

Audio is customer-controlled content: private storage, minimum metadata in logs, explicit rights confirmation, quick anonymous retention, easy project/account deletion, and no training use by default. The legal copy included in the product is intentionally marked for final counsel review.

