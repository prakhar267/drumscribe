# DrumToScore launch-readiness audit — 12 September 2026

This record contains no passwords, connection strings, API keys, private object
names, card data or customer content. No card, checkout, paid plan or billable
resource was used during this work.

## Decision summary

| Area | Result | Launch meaning |
| --- | --- | --- |
| Hosted CI | Pass | The public repository release checks are green |
| Desktop/browser QA | Pass | Core journeys passed in Chromium, Firefox and WebKit |
| Responsive QA | Pass | Core journeys passed at iPad Pro 11 and Pixel 7 profiles |
| Private-object restore canary | Pass | Upload, signed playback, export, delete and byte-exact restore all worked |
| Public readiness | Pass | Database, queue, storage and model provider all reported ready |
| Unused host listener | Remediated | `rpcbind` is disabled and port 111 is closed |
| Fresh isolated-drum control | 91.34% five-family F1 | Detector control passes the 90% target on these two recordings only |
| Fresh constructed full mixes | 61.64% five-family F1 | Broad 90% full-song marketing claim remains blocked |
| Dodo live review | Pending | Public live checkout must remain disabled |

## Source and CI

The Docker Compose MinIO references were moved from Docker Hub to official,
digest-pinned Quay images so GitHub Actions no longer depends on the blocked
Docker Hub path. Hosted run
[`34699847192`](https://github.com/prakhar267/drumscribe/actions/runs/34699847192)
passed Python, Compose validation, web checks, dependency security, browser E2E
and stack E2E.

The browser workflow now installs Chromium, Firefox and WebKit and executes the
desktop, tablet and mobile projects. The local final matrix executed 63 test
cases: 27 passed and 36 were intentional project-specific skips. Visual snapshot
assertions remain fixed to desktop Chromium; functional journeys run in the
applicable browser and device projects. Manual screenshots of the homepage,
upload page and editor were inspected at desktop, iPad and Pixel dimensions. The
tablet editor toolbar was corrected so Undo and Redo remain available.

## Production operations

The Oracle host was checked before changing `rpcbind`: there were no NFS mounts,
no NFS entry in `/etc/fstab`, no required reverse dependency and no firewall rule
exposing port 111. `rpcbind.socket` and `rpcbind.service` were then disabled and
stopped. The change is reversible. API, worker, scheduler and Caddy containers
remained running and the public readiness endpoint returned HTTP 200.

The private-storage recovery canary used unique synthetic audio and MusicXML
objects under an operations-only prefix. It verified storage health, signed
audio playback, signed export download, XML parsing, deletion, byte-exact restore
and final cleanup. The restored audio SHA-256 was
`56d4af65701c26df20bd4021eda95b6e830348ce3a746086079fe89285548dc9`.
No customer object was read, changed or deleted.

## Fresh accuracy control

Selection was frozen before inference. The 105-second check used two previously
unselected Groove MIDI Dataset test performances with aligned reference events:
rock-groove8 and funk. For a full-mix diagnostic, the real human performances
were combined with rights-cleared musical backing after subtracting a learned
estimate of the backing's original drums.

At a 50 ms matching tolerance:

| Condition | Five-family micro F1 | Detailed micro F1 |
| --- | ---: | ---: |
| Original isolated human drum performances | 91.34% | 89.59% |
| Constructed full mixtures through production-equivalent separation and fusion | 61.64% | 54.87% |

The isolated control confirms that the onset/class detector can exceed 90% on
these performances. It does **not** establish 90% full-song accuracy. In the
constructed mixtures, the family F1 values were hi-hat 72.11%, kick 55.85%,
snare 54.84%, cymbal 20.00% and tom 18.18%. Separation plus residual percussion
from learned backing subtraction is the dominant loss. The full-mix result is a
diagnostic on two constructed mixtures, not a general product percentage or an
untouched released-song claim.

A development-only family threshold/weight search raised the same opened
diagnostic to an estimated 66.6%, which is not enough and is not independent
evidence. It was therefore not promoted to production. A future improvement must
be frozen on development material and then pass a newly sealed, rights-cleared
full-mix set before deployment.

Reproduction entry points:

```sh
python scripts/run_launch_rights_cleared_benchmark.py --device mps
python scripts/storage_restore_canary.py --help
```

Benchmark audio and intermediate output stay untracked because they are large
evaluation artifacts. The runner, selection hashes and non-secret result record
provide the reproducible audit path.

## Explicitly pending

1. Wait for Dodo's live review. Do not enable public billing or use a real card.
2. Complete a no-charge live checkout-session display check after approval, then
   deploy billing only after the signed live webhook and credit mapping pass.
3. Improve and independently validate full-mixture separation/transcription;
   do not advertise a broad 90% accuracy claim from the isolated control.
4. Obtain qualified legal/tax review before relying on the current international
   terms, consumer-refund wording or GST position.
5. Confirm that GitHub failure notifications reach the monitored founder inbox.
6. Approve a paid capacity plan before promising an SLA or exceeding the single
   free-worker capacity. Any card or charge requires separate explicit approval.
