# CollectiveOS Model Forge

## Outcome

Model Forge is the isolated execution side of the QMF v0.10 model-derivation contract. It gives
CollectiveOS a reproducible place to validate plans, exercise checkpoint and telemetry flows,
and measure the RTX 4090 sandbox before any real model training is authorized.

Version 0.4 implements two states:

| State | What executes | Evidence class | QMF-admissible |
| --- | --- | --- | --- |
| `simulate` | Deterministic virtual steps, telemetry, synthetic checkpoint metadata | `SIMULATED` | No |
| `probe` | Sandbox and NVIDIA hardware inspection only | `PHYSICAL_PREFLIGHT` | No |

There is deliberately no `train` state yet. A completed QMF training run requires byte-exact
base weights, a rights-reviewed dataset, an immutable container/toolchain lock, a measured
budget, a physical checkpoint chain, and independent signatures. Simulation and preflight
cannot be promoted by relabeling their receipts.

## Trust split

- `collectiveos-isomorphic-core` executes bounded Forge states and emits evidence.
- Quantum Model Family recomputes and verifies model derivation and admission.
- SYN Coder consumes only a separately qualified derivative and remains proposal-only.
- Model output, synthetic observations, and hardware telemetry never grant authority.

The governance route remains `QC -> GATA -> GATA_PRIME`: exact plan validation, bounded state
execution, then sealed receipt replay.

## Plan contract

Every plan is strict JSON conforming to `schemas/model-forge-plan.schema.json`. The runtime also
recomputes its `plan_hash` using QMF's canonical JSON and rejects unknown fields, booleans
disguised as integers, unpinned revisions, unsafe paths, memory aggregation, swap, networking,
remote code, adapter merging, or any loss of the immutable-base rollback.

The checked-in simulation and probe fixtures target:

- `openai/gpt-oss-20b@6cee5e81ee83917806bbde320786a8fb61efebee`;
- Harmony-formatted, assistant-response-only SFT;
- LoRA rank 8 / alpha 16 with `all-linear` plus reviewed MoE projections at layers 7, 15, and 23;
- one discrete 24 GiB VRAM domain and one separate 128 GiB host-RAM domain;
- no adapter merge, remote code, model publication, or deployment claim.

The recipe follows the public GPT-OSS LoRA shape, but its checked-in hashes are simulation labels,
not physical source, artifact, dataset, toolchain, or admission evidence. OpenAI's reference
fine-tune targets an 80 GiB H100; RTX 4090 fit must be measured, not inferred. See the
[OpenAI GPT-OSS fine-tuning recipe](https://developers.openai.com/cookbook/articles/gpt-oss/fine-tune-transfomers),
[TRL SFTTrainer documentation](https://huggingface.co/docs/trl/sft_trainer), and
[PEFT LoRA documentation](https://huggingface.co/docs/peft/developer_guides/lora).

## Local validation

```powershell
python -m oims forge validate `
  --plan forge/examples/gpt-oss-20b-4090-simulation.plan.json
```

Run a simulation without Docker:

```powershell
python -m oims forge simulate `
  --plan forge/examples/gpt-oss-20b-4090-simulation.plan.json `
  --output artifacts/model-forge
```

The direct simulation path requires either a launcher-built image with a matching read-only source
commit/tree attestation or a clean Git working tree whose commit and tree can both be resolved. It
refuses before creating the run directory when executed from dirty or unprovable source, preventing
receipts from attributing modified code to a clean `HEAD`.

Verify the returned receipt and every linked telemetry/checkpoint/candidate artifact:

```powershell
python -m oims forge verify `
  --receipt artifacts/model-forge/sim-783d6fd324c9fb78/receipt.json
```

Verification must run from the same clean source commit/tree that produced the receipt, or from its
launcher-built image with the matching fixed attestation. A receipt cannot be relabeled to another
valid Git commit/tree pair and verified from the original producer source.

The simulation writes no `adapter_config.json` or `adapter_model.safetensors`. Its candidate is
named `synthetic-candidate.json` and contains explicit `not_a_model`, `not_a_peft_adapter`, and
`qmf_admissible: false` boundaries. Simulation plans are capped at 4,096 steps and 64 MiB of
evidence. Before writing, the runtime serializes and meters the plan, telemetry, checkpoints,
candidate, and sealed receipt; verification independently sums those files and rejects any mismatch.

## OCI / WSL2 environment

The Compose environment is hardened independently of the Python validator:

- no container network;
- read-only root filesystem;
- all Linux capabilities dropped;
- no-new-privileges enabled;
- non-root UID/GID 65532;
- bounded PIDs, RAM, swap, shared memory, and tmpfs;
- exact read-only base-model, dataset, and plan mounts;
- one explicitly selected NVIDIA device for `probe`;
- `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, and `HF_DATASETS_OFFLINE=1`.

Docker Compose requires an image reference pinned by digest. It intentionally refuses an implicit
floating base tag. The launcher also derives an exact lowercase source commit and tree (or accepts
`-SourceCommit`) and embeds a read-only attestation in the image so receipts retain provenance even
though `.git` is excluded from the build context:

```powershell
.\scripts\run_model_forge.ps1 `
  -Mode Simulate `
  -Plan .\forge\examples\gpt-oss-20b-4090-simulation.plan.json `
  -BaseImage "python:3.12-slim@sha256:<verified-digest>" `
  -BaseModelDir D:\Collective\Models\GPT-OSS-20B `
  -DatasetDir D:\Collective\Datasets\Forge `
  -OutputDir D:\Collective\ProofVault\ModelForge
```

The image build may access package indexes to install the small controller dependency set. The
running container has no network. A physical toolchain lock must later hash the selected base
image and every downloaded training wheel before the `train` state can be introduced.

The launcher requires Git, verifies that `-SourceCommit` (when supplied) equals `HEAD`, refuses any
tracked or untracked working-tree change, rejects assume-unchanged/skip-worktree index flags, and
uses `git archive` to construct a temporary Docker context from that exact commit. It records the
exported commit and Git tree in an attestation outside the installed package. The build installs
that package into the interpreter prefix, removes its temporary source tree, and launches Python in
isolated mode from `/forge`; the non-root runtime must match the attestation and prove that the
imported module is isolated from `/workspace` before using the container provenance shortcut.
Compose refuses a working-tree context. This keeps the source recorded in Forge receipts bound to
the exact source copied into the image.

Docker documents GPU reservations through `deploy.resources.reservations.devices`; the Forge
sets `capabilities: [gpu]` and an explicit device ID. See
[Docker Compose GPU support](https://docs.docker.com/compose/how-tos/gpu-support/).

## Physical preflight

`probe` requires all of the following at the same time:

1. A plan whose mode is `probe` and whose simulation payload is null.
2. The exact recomputed plan hash passed through `--accept-plan-hash`.
3. `OIMS_FORGE_ENABLE_PROBE=1` inside the locked Compose profile.
4. An immutable base-image digest plus offline Hugging Face environment flags.
5. Non-root execution, empty Linux capabilities, no-new-privileges, and an active default seccomp
   filter.
6. A read-only root, read-only plan/base/dataset mounts, a writable evidence mount, a successful
   process-level create/write/fsync/delete probe as UID 65532, and tmpfs at `/tmp`.
7. No default route, no interface other than loopback, and no swap use.
8. Current cgroup usage subtracted from the cgroup RAM limit must leave the full plan ceiling;
   cgroup swap is zero and the PID limit is no greater than 512.
9. Observed host `MemTotal` within a bounded 2 GiB reserved-memory tolerance of the declared
   physical host domain, plus enough currently available host RAM for the peak ceiling.
10. A parseable RTX 4090 `nvidia-smi` record with matching VRAM capacity, enough currently
    available VRAM, and temperature headroom for the plan ceilings.

The checked-in probe plan hash is
`sha256:a7d8598120a94de263af8f3d2de54e5be0da4142c10c8aeef4d1467e8266f4b6`. Run it
through the same launcher paths used above:

```powershell
.\scripts\run_model_forge.ps1 `
  -Mode Probe `
  -Plan .\forge\examples\gpt-oss-20b-4090-probe.plan.json `
  -BaseImage "python:3.12-slim@sha256:<verified-digest>" `
  -BaseModelDir D:\Collective\Models\GPT-OSS-20B `
  -DatasetDir D:\Collective\Datasets\Forge `
  -OutputDir D:\Collective\ProofVault\ModelForge `
  -AcceptPlanHash "sha256:a7d8598120a94de263af8f3d2de54e5be0da4142c10c8aeef4d1467e8266f4b6"
```

It records GPU UUID/name, physical VRAM, current allocation, temperature, and power evidence.
It does not import Transformers, load weights, allocate the model, create gradients, or claim
that GPT-OSS training fits. The next phase will add a separately reviewed, one-step LoRA memory
probe only after the real base snapshot and dataset manifest exist.

## Research constraints encoded

- UI state is a projection of explicit Forge state; no hidden execution transition exists.
- The model never mutates governance state or certifies its own output.
- VRAM and host RAM are separately identified physical domains; storage is not counted as RAM.
- Dynamic packing, response-only loss, Harmony preservation, PEFT rollback, and PowerShell
  code-comment-test curriculum remain plan-level invariants.
- Duration, steps, tokens, bytes, host/device peaks, energy, cost, temperature, network, and swap
  are hard ceilings.
- Every checkpoint links to its predecessor, and verification replays the complete chain.
- FPGA/AIE/NPU acceleration may later produce telemetry or deterministic data-movement evidence,
  but cannot approve a model or amplify authority.

## Next promotion gate

The next lawful state is not a long training run. It is a physical one-step preflight with:

1. the pinned GPT-OSS snapshot hashed byte-for-byte;
2. a small rights-clean Harmony dataset and holdout;
3. exact wheel and container digests for Torch, Transformers, TRL, PEFT, Datasets, Accelerate,
   Safetensors, and Hugging Face Hub;
4. measured VRAM/RAM/swap/temperature/power telemetry;
5. automatic abort before the first optimizer step if any ceiling is crossed; and
6. a non-promotable preflight receipt for QMF review.
