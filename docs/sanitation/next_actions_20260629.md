<!-- DOCUMENTATION ONLY -->
<!-- DO NOT APPLY WITHOUT HUMAN APPROVAL -->

# Next Actions - 2026-06-29

**DOCUMENTATION ONLY. DO NOT APPLY WITHOUT HUMAN APPROVAL.**

## CSV Snapshot

```csv
priority,action,category,requires_human_gate,notes
1,Keep provider hardening test-only patch monitored,test_hardening,NO,Commit aa06d95 live; provider leak grep passed.
2,Mock/offline any remaining provider paths in broader test suite,test_hardening,YES if runtime changes needed,Current required operational tests are hardened.
3,Owner review heavy live-only packages,requirements,YES,torch/tensorflow/TTS/gruut/nvidia/triton/playwright etc.
4,Decide ONNX model owner,models,YES,Probable orphan but git tracked; no removal without backup/approval.
5,Review legacy archive safe backup,legacy_archive,YES,Backup created for 5 small safe files only; no move/delete.
6,Define logrotate/cache TTL implementation,log_cache,YES,Policy proposal only; no systemd/logrotate change.
7,Delete tmp staging venvs,tmp_cleanup,YES,Only after confirming reports/freeze are no longer needed.
8,Plan venv switch only with rollback,python_env,YES,Staging refined is testable but DO_NOT_SWITCH.

```

## Interpretation
- Actions marked as requiring a human gate must not be executed automatically.
- Staging cleanup, archive movement, logrotate configuration, and venv switch all require explicit approval.
