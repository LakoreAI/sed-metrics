# Model comparison and metric checks

Three scripts that use the published `sedmetrics` package. Each declares its
own dependencies, so [`uv`](https://docs.astral.sh/uv/) can run it directly.
Downloads and outputs go to `benchmarks/runs/`, which git ignores.

| Script | What it does |
| --- | --- |
| `compare_models.py` | Runs five pretrained detectors and scores them |
| `check_parity.py` | Compares scores with `sed_eval`, `sed_scores_eval` and scikit-learn |
| `perturbation_study.py` | Scores synthetic detectors that each contain one error |

## Models

AudioSet Strong checkpoints from
[PretrainedSED](https://github.com/fschmid56/PretrainedSED) (MIT), pinned to
commit `1aa47e4`: `ATST-F`, `BEATs`, `fPaSST`, `M2D` and `frame_mn10`.
Checkpoints are checked against SHA-256 sums.

Model inference in `compare_models.py` has not been run yet. The other stages
have been tested with random stand-in scores. Start with `--limit 32`.

## URBAN-SED (zero-shot)

Needs the extracted `URBAN-SED_v2.0.0` directory (CC BY 4.0). The models were
trained on AudioSet, so each URBAN-SED class takes the maximum over a fixed list
of AudioSet classes (`URBAN_SED_MAPPING` in the script). Thresholds are chosen
on the validation split and applied to the test split.

```bash
uv run benchmarks/compare_models.py predict  --dataset urban-sed --urban-sed DIR --limit 32
uv run benchmarks/compare_models.py predict  --dataset urban-sed --urban-sed DIR
uv run benchmarks/compare_models.py evaluate --dataset urban-sed
uv run benchmarks/compare_models.py report
```

## AudioSet Strong evaluation split

The audio comes from the `CLAPv2/audioset_strong` dataset on Hugging Face, about
15.6 GB. Ground truth follows the PretrainedSED evaluation: training classes
only, overlapping events of one class merged, clips without events dropped.

```bash
uv run benchmarks/compare_models.py fetch    --dataset audioset-strong
uv run benchmarks/compare_models.py predict  --dataset audioset-strong
uv run benchmarks/compare_models.py evaluate --dataset audioset-strong
uv run benchmarks/compare_models.py report
```

Scores take about 3.5 GB of disk per model. PSDS1 is computed one class at a
time and averaged without the standard deviation penalty, which is how the
upstream repository reports its macro-averaged value. Joint PSDS over all
classes is not attempted: memory grows quickly with the class count.

Results are written to `benchmarks/runs/results/` (`tables.md`, CSV and JSON).

## Cross-check against the reference toolkits

```bash
uv run benchmarks/perturbation_study.py --urban-sed DIR
uv run benchmarks/check_parity.py \
  --scores benchmarks/runs/scores/synthetic-urban-sed-test \
  --output benchmarks/runs/results/parity-synthetic.json

# The same check on model scores, after `evaluate --dataset urban-sed`:
uv run benchmarks/check_parity.py \
  --scores benchmarks/runs/scores/urban-sed-test --median 9 \
  --results benchmarks/runs/results/urban-sed \
  --output benchmarks/runs/results/parity-models.json
```

## Things that change the numbers

- URBAN-SED annotates overlapping events of one class. Frame scores cannot
  separate them, so event F1 has an error-free value below 1.
- PSDS here uses references with those events merged, as `sed_scores_eval`
  requires. `sedmetrics` itself accepts overlaps and returns a different value.
- Some offsets are stored as `10.000000000000002`. Times are rounded to
  microseconds so that they do not open an eleventh segment.
