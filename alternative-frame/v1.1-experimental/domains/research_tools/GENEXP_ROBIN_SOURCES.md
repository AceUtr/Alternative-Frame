# GenExp / Robin source and dependency record

Baseline: `f1f3520e21ac1229283d8de433b0971a38c713af`.
Branch: `feature/research-genexp-robin`.

- GenExp: https://github.com/DanielBrunnsaker/GenExp (root MIT).
  Adapted the hypothesis / proposal selection / structured protocol / evidence
  recording workflow. No upstream code, datasets, ontology files or nested
  components (including amiga-master) are copied or required.
- Robin: https://github.com/Future-House/robin (Apache-2.0).
  Adapted independent candidate evaluation, pairwise comparison and explicit
  selection records. No upstream source or Edison adapters are copied. The
  implementation uses deterministic training CV and round-robin comparisons,
  not an LLM judge, BTL fitting, or a replication of the paper's biomedical results.
- The classifier evaluation reuses this project's existing fixture functions in
  `examples/research_task/run_baseline.py`.

No new runtime packages: Python 3.10+ standard library only. Existing pytest is
needed for development tests, not for running the Demo. No API key, Prolog,
Aleph, Edison client, GPU, model weights or network access is needed at runtime.

If future work copies upstream code or nested components, review the exact
revision and component license, preserve copyright/license text, and satisfy
any applicable NOTICE requirements before including it. This record does not
claim a license audit of unimported nested repositories.
