# Dataset adapters

Adapters turn on-disk reference data into a `sedmetrics.Dataset`: validated
reference events with stable integer ids, recording durations, a class
vocabulary and human-readable names. They are deliberately separate from the
metrics, so the core never depends on pandas, pyarrow or a file layout.

```python
import sedmetrics as sm

dataset = sm.adapters.load_urban_sed("data/raw/URBAN-SED_v2.0.0.tar.gz", split="test")
result = dataset.event_f1(predictions)          # predictions may use names or ids
print(result.f1, result.n_correct, result.n_insertions, result.n_deletions)
```

`Dataset.event_f1` forwards to `sm.event.f1` with the dataset's recording
durations, so events outside their recording are rejected rather than clipped.

## Strictness

Adapters never skip data silently. A malformed annotation row, a missing
duration, a non-finite timestamp or an unknown split raises `ValueError` with
the file and row. The only files ignored are macOS AppleDouble resource forks
(`._*.txt`, `.DS_Store`), which are archive metadata rather than annotations.

## URBAN-SED v2.0.0

Input: the extracted release directory (containing `annotations/`) or the
official `URBAN-SED_v2.0.0.tar.gz`.

- Annotation files are `annotations/<split>/<clip>.txt` with tab-separated
  `onset<TAB>offset<TAB>label` rows; the loader accepts `train`, `test`,
  `validate` or `all`.
- Recording ids follow sorted clip names, and `recording_names` holds the clip
  stem, so they are stable across runs and independent of filesystem order. A
  clip stem that appears in two splits is rejected.
- The class vocabulary is the sorted set of labels in the loaded cohort; ids can
  therefore shift when `limit` is used.
- **Clips without events are kept.** They appear in `dataset.durations` and can
  be predicted on; that matters for false-alarm and exposure analysis.
- Duration: `clip_duration` (default 10 s) is a documented convention, not read
  from the audio. If an annotation ends later than the nominal duration — some
  URBAN-SED rows end at `10.000000000000002` for a 10 s clip — the clip duration
  is extended to that offset instead of truncating the annotation.
- Reading the `.tar.gz` streams the archive and stops at the end of the
  `annotations/` tree, so the 6.6 GB of audio is not decompressed. This relies
  on the official layout, which stores annotations before audio; extract the
  archive if you have a re-ordered copy.

## AudioSet strong

Input: a directory of `*.parquet` batches (for example CLAPv2's
`audioset_strong` export) or a single file. Requires `pyarrow`
(`pip install "sedmetrics[data]"`).

Used columns:

- `audio_len` — decoded audio duration in seconds.
- `raw_text` — list of header lines; the loader reads the line starting with
  `Strong events:`, whose entries look like
  `(0.000s - 1.435s) Male speech, man speaking (/m/05zppz)`.

Mapping decisions:

- **Classes are keyed by ontology id (`/m/...`), not display name.** Two ids can
  share a display name; `Dataset.class_id` then refuses the ambiguous name and
  asks for the id.
- Recording ids follow file order and row order; names are
  `"<file stem>#<row>"`. There is no clip identifier in the parquet batches, so
  ids are positional, not content-derived.
- Duration comes from `audio_len`, except that a clip whose annotations end
  later gets the latest annotated offset as its duration. Annotations are on the
  original segment timeline, and roughly 10 % of the sampled rows end up to
  0.43 s past the decoded audio; truncating them would discard labelled audio.
  A row more than 1 s past its duration is treated as corrupt and raises.
- Rows without a `Strong events:` line are empty clips and are kept.

## Limits and subsampling

Both loaders accept `limit=<n>` to load the first `n` recordings. This is for
smoke tests: because class ids are assigned from the loaded cohort, a limited
dataset has a different vocabulary than the full one. Never compare results
computed on different `limit` values.

## Verification status

The adapters are covered by unit tests (parsing, ids, durations, empty clips,
metadata files, archives) and by parity tests that run the loaded data through
both SEDMetrics and `sed_eval` 0.2.1. Current parity runs use 120 URBAN-SED test
clips (638 reference events, 10 classes) and 60 AudioSet strong clips
(625 reference events, 86 classes), with synthetic predictions derived from the
references. URBAN-SED labels are used as distributed; no split or label
cleaning is applied.
