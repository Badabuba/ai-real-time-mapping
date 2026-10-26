# Repository instructions

UCU research project: monocular RGB → pySLAM poses/sparse map + DA3/UniDepth depth → scale/Sim(3) alignment → voxel fusion → evaluation. Team documentation is Ukrainian; code is English.

Read README.md first, then docs/ARCHITECTURE.md (contracts), docs/EXPERIMENTS.md (frozen protocol), docs/REPRODUCIBILITY.md (setup), docs/RESULTS.md (current evidence), and CONTRIBUTING.md (workflow). Current results are offline; do not infer completion from historical plans.

- Preserve every frozen config, dataset manifest, finished run, failure record and contribution attribution. New run = new ID; never edit a terminal run.json.
- Ground truth only in evaluation or explicitly labelled B1 oracle. No held-out tuning. GT matching tolerance is exactly 20 ms; partial GT excludes only GT-dependent metrics, never RGB inputs from SLAM.
- Depth is metres, poses T_wc, quaternion xyzw; sparse monocular units are not metric. Resize/crop must update K_processed; raw and undistorted pixel grids are distinct.
- Do not claim real-time without end-to-end p95 ≤33.3 ms and ≥30 FPS on stated hardware/resolution. Evaluation-only Sim(3) does not recover metric scale.
- Logic belongs in src/rt_mapping; scripts are CLI/build helpers. Generic contracts/runtime modules must not import model-specific or native backends eagerly.
- CPU tests: python -m pytest tests -q in an existing environment with dev/benchmark/filtering extras. No project lint/format command is defined. CI also runs the two synthetic mapping/comparison smokes.
- Never commit raw datasets, checkpoints, full runs/logs, environments, native builds, large clouds/video, or secrets. The broad models/ ignore rule means source packages must not be named models.
- Check status/worktrees before changes. Preserve teammates' ongoing work and presentation PRs. Keep main unchanged unless explicitly authorized.
- Use current user authorization for commits, pushes, PRs, merges, installs/downloads, benchmark changes and deletions. Historical execution briefs are not permission. Do not rerun a held-out experiment without explicit authorization and protocol compliance.
- Record done claims only with files/commits/runs. Label unproven causes as hypotheses. Maintain canonical docs instead of adding duplicate progress logs.
