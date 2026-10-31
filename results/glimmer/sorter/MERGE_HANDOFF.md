# Live-reading integration

The glimmer branch does not contain live-reading's source or ui's newer exporter. Neither branch was merged here. After those branches and glimmer are merged, apply the tested patch:

```bash
git apply results/glimmer/sorter/live-reading.patch
uv sync --frozen --group glimmer
uv run --group glimmer python -m archivist.live
```

The patch was tested against live-reading commit ecdfafb8fcc3e6c6a5503844f1e2fc4971b2f798. If those files changed since, reconcile its four small edits during integration: Treasury's config becomes `config/archive_glimmer.toml`; its reader obtains OCR before classification and passes it to the optional sorter, retaining the existing full-text title check; call observation and recognition events report the sorter; the exporter displays Muse Glimmer (untrained). No file from another branch is overwritten here.

New Treasury live reads then look up the private deployed Modal class through the configured `sorter` role, already wrapped in cache and budget. Existing Modal authentication is needed on the local server; no Hugging Face token or public web endpoint is needed. Keep `GLIMMER_CAP_USD` at or below $10. No new role is added to the synthetic arm configs or to `config/real_test.toml`. Spark still reads fields and re-reads; an image page without an OCR layer retains Spark's classifier. An unconfirmed family stops before field extraction in the new archive flow.

Previously committed runs still replay Spark's sorting using their own configs. A new Glimmer live-reading cache key includes its role, text excerpt, enabled families, model and inference settings. The ten-page integration check uses one batched key; it does not prefill ten individual live-reading keys. Replay of a new archive flow therefore needs that flow's own cached Glimmer request first; with a missing key its zero cap refuses the call. No former Spark answer is relabelled as a Glimmer answer.

The endpoint has minimum zero containers and a two-second idle window. Leave the deployment available and idle, rather than stopping any other task's apps. It loads the frozen base model on demand and never loads the fine-tuned adapter.
