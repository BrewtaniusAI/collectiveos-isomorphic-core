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

Direct working-tree execution is intentionally limited to plan validation. Simulation and receipt
verification refuse outside the isolated launcher-built container because already-imported project
code cannot safely attest its own source. Before container creation, the trusted launcher validates
the normalized Compose process, entrypoint, non-root user, build context, and exact four-mount
policy. The container's external pre-import verifier then establishes the installed package,
commit, tree, interpreter, dependency, and in-namespace mount boundaries before either operation
can emit or accept evidence. Use the launcher flow below for simulation and verification.

The trusted launcher, Docker CLI/daemon, and NVIDIA runtime are part of this evidence boundary. A
raw OCI invocation, an entrypoint or volume override, or an actor able to replace the daemon,
runtime, root filesystem, or first executable is outside the Forge evidence contract; output from
such a run is not accepted as governed Forge evidence. This boundary is explicit because no process
inside a mount namespace can authenticate code that an OCI administrator replaced before the
kernel started that process.

The simulation writes no `adapter_config.json` or `adapter_model.safetensors`. Its candidate is
named `synthetic-candidate.json` and contains explicit `not_a_model`, `not_a_peft_adapter`, and
`qmf_admissible: false` boundaries. Simulation plans are capped at 4,096 steps and 64 MiB of
evidence. Before writing, the runtime serializes and meters the plan, telemetry, checkpoints,
candidate, and sealed receipt; verification independently sums those files and rejects any mismatch.
Completed run directories are published with Linux atomic no-replace rename semantics, so a
concurrently created destination is preserved. Receipt replay explicitly requires a validated
`simulate` plan before any plan-derived semantic checks can be considered satisfied.

Forge evidence schema 1.1 adds typed `constraint_signals` to plan decisions, simulations, and
physical-preflight receipts. Every signal records a canonical identifier, constraint type, evidence
source, validation method, satisfied status, and a digest of that exact signal body. Signals are
uniquely sorted and their complete set is hash-bound into `proof_vault` metadata. Semantic replay
reconstructs the expected simulation signals, so a structurally valid and resealed substitution is
still refused.

The `proof_vault` object is metadata, not a storage claim. It always records `NOT_APPENDED`,
`worm_write_performed: false`, `external_anchor: null`, and `promotion_eligible: false` in this
repository. An external owner-approved WORM destination remains a separate authority boundary.
Neither a receipt seal nor a Constraint Signal digest may be relabeled as an external Proof Vault
anchor.

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

Before a simulation can emit evidence, the pre-import entrypoint authenticates descriptor-bound
procfs, sysfs, and cgroup2 filesystem magic and cross-checks mountinfo IDs against kernel `statx`
mount IDs in the current process namespace. The runtime then observes UID/GID 65532, empty inheritable,
permitted, effective, bounding, and ambient capability sets, no-new-privileges, seccomp filter mode
plus the runtime-default allowlist's `EPERM` default-deny behavior and required keyring, `clone3`,
`io_uring_setup`, and `userfaultfd` restrictions, a read-only root, loopback-only networking, the
exact Forge mount policy with no unexpected writable mount, unused and cgroup-disabled swap, a
bounded memory cgroup, the exact `/forge/output` evidence destination, and at most 512 PIDs.

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

Verify the resulting receipt inside the same source-attested image. `-Receipt` must resolve beneath
`-OutputDir`, which is mounted at `/forge/output` in the isolated verifier:

```powershell
.\scripts\run_model_forge.ps1 `
  -Mode Verify `
  -Plan .\forge\examples\gpt-oss-20b-4090-simulation.plan.json `
  -BaseImage "python:3.12-slim@sha256:<verified-digest>" `
  -BaseModelDir D:\Collective\Models\GPT-OSS-20B `
  -DatasetDir D:\Collective\Datasets\Forge `
  -OutputDir D:\Collective\ProofVault\ModelForge `
  -Receipt D:\Collective\ProofVault\ModelForge\sim-8d6753e4990923ed\receipt.json
```

The image build may access package indexes to install the small controller dependency set. The
running container has no network. A physical toolchain lock must later hash the selected base
image and every downloaded training wheel before the `train` state can be introduced.

The launcher requires Git, verifies that `-SourceCommit` (when supplied) equals `HEAD`, refuses any
tracked or untracked working-tree change, rejects assume-unchanged/skip-worktree index flags, and
streams `git archive` for that exact commit directly into `docker build`, with no mutable extracted
directory. The stream adds the exported commit and Git tree as a virtual attestation file, and the
launcher supplies the pinned base image, commit, and tree as direct build arguments rather than
mutable Compose fields. The build returns its content-addressed image ID, and the launcher inserts
that immutable ID into the already-validated in-memory execution snapshot so a concurrent retag
cannot substitute the image. The build installs
that package into the interpreter prefix, removes its temporary source tree, and launches Python in
isolated, site-disabled mode from `/forge`; the non-root runtime must match the attestation and prove that the
imported module is isolated from `/workspace` before using the container provenance shortcut.
Before importing any project code, an external isolated entrypoint hashes every installed `oims`
package byte and compares it with a digest sealed into the build attestation. Only then does a
site-disabled bootstrap add the authenticated package directory for import; the in-package check
repeats that comparison as defense in depth. Both attestation readers use a nonblocking, bounded
regular-file descriptor rather than a path-based metadata/read sequence. The entrypoint also reads `/proc/self/mountinfo` and
`/proc/self/maps`. It refuses any mount covering or nested beneath the interpreter prefix,
installed package, attestation, verifier, standard executable/library roots, dynamic-loader
configuration, the Python executable, or any file-backed process mapping. This protects Python
dependencies, the native loader and shared libraries, system executables, the evidence, and the
expected digest. For physical probes it also authenticates the `/proc`, `/sys`, and cgroup
filesystems and refuses extra mounts covering any status, memory, swap, route, interface, mount,
mapping, membership, or cgroup observation source. The cgroup v2 mount must expose root `/`, and
the process must report unified membership `/`, preventing a substituted sub-cgroup from hiding
the real container limits. The probe lane makes one narrow exception for NVIDIA Container
Toolkit: exact read-only `nvidia-smi`, `nvidia-debugdump`, `nvidia-persistenced`, CUDA MPS utility, and
NVIDIA/CUDA shared-library file mounts are bounded and byte-hashed by this pre-import verifier.
Every individual path and digest must match the source-controlled
`forge/nvidia-runtime.approved` manifest embedded in the clean, commit-exported image; the checked-in
comment-only manifest deliberately denies all physical probes until maintainers commit the exact
trusted Toolkit/driver file hashes and rebuild. The authenticated aggregate digest is carried into
the physical-preflight receipt. The verifier also copies the single attested `nvidia-smi` artifact
into an inherited write-sealed memfd, and the probe invokes its `/proc/self/fd/<fd>` path directly
so neither `PATH` nor a later host write can substitute the inspected utility. Every approved
NVIDIA library is copied into its own sealed memfd; a private tmpfs directory contains only
descriptor symlinks for those exact files, and the child gets that directory as its sole
`LD_LIBRARY_PATH`. Other inherited dynamic-loader overrides are absent.
An NVIDIA file already mapped before verification, a writable or non-regular file, an entire
runtime-root mount, or any non-NVIDIA executable-runtime mount still fails closed. Compose refuses
a working-tree context, and the launcher rejects any resolved service, entrypoint, user, build
context, sandbox setting, or bind mount outside the checked-in four-mount policy before starting
Python. The host check covers the complete rendered service field allowlist, exact PID, RAM, swap,
shared-memory, and tmpfs limits, and the probe's exact single-device NVIDIA reservation with no
additional capability or device field. Rendered Linux paths are compared case-sensitively. The
launcher records OS filesystem identities and descriptor-bound canonical paths for the plan and all
three host directories, then re-resolves and rechecks both those snapshots after the image build.
Output/input disjointness is recomputed from the current canonical paths immediately before
execution. Exact backing device/inode identity and component-safe backing-tree coordinates derived
from the kernel mount ID, mount root, and path within that mount are compared independently of the
visible Linux mountpoint. A memoized, globally bounded mount-parent traversal includes every nested
filesystem visible beneath each source, so equal, ancestor, descendant, and cross-submount aliases
through distinct bind mounts all fail closed without quadratic work. Moving an identity-preserving
object behind a symlink or junction therefore fails as well. It then rebinds every Linux mount
source to the held launcher's `/proc/<pid>/fd/<fd>` object; on
Windows, non-delete-sharing filesystem handles retain the verified names until Compose returns.
The validated snapshot is translated to an argument-array `docker run` whose four `--mount`
arguments set Engine-level `bind-recursive=disabled`; late descendant mounts are therefore excluded
at the bind operation itself, and the probe request carries the validated NVIDIA driver as well as
its exact device ID. Those leases and nonrecursive binds close the final check-to-bind race. The
launcher executes that exact rendered policy
from memory rather than reparsing the mutable Compose path. This keeps source and runtime evidence
bound to the exact inspected host objects and bytes.

Docker documents GPU reservations through `deploy.resources.reservations.devices`; the Forge
sets `capabilities: [gpu]` and an explicit device ID. See
[Docker Compose GPU support](https://docs.docker.com/compose/how-tos/gpu-support/).

## Physical preflight

`probe` requires all of the following at the same time:

1. A plan whose mode is `probe` and whose simulation payload is null.
2. The exact recomputed plan hash passed through `--accept-plan-hash`.
3. `OIMS_FORGE_ENABLE_PROBE=1` inside the locked Compose profile.
4. An immutable base-image digest plus offline Hugging Face environment flags.
5. Non-root execution, empty inheritable/permitted/effective/bounding/ambient Linux capability sets,
   no-new-privileges, seccomp filter mode, the runtime-default allowlist's `EPERM` default-deny
   behavior, the required keyring-syscall denials, and the expected `clone3`, `io_uring_setup`, and
   `userfaultfd` restrictions.
6. A read-only root, read-only plan/base/dataset mounts, a writable evidence mount, a successful
   process-level create/write/fsync/delete probe as UID 65532, no writable ancestor or descendant
   mount covering either protected input, no unexpected writable mount outside the evidence/runtime
   allowlist, an output path resolving exactly to `/forge/output`, and tmpfs at `/tmp`.
7. No default route, no interface other than loopback, and no swap use.
8. Current cgroup usage subtracted from the cgroup RAM limit must leave the full plan ceiling;
   cgroup swap is zero and the PID limit is no greater than 512.
9. Observed host `MemTotal` within a symmetric 2 GiB reserved-memory tolerance of the declared
   physical host domain, plus enough currently available host RAM for the peak ceiling.
10. Every injected NVIDIA utility and library must match its exact path and SHA-256 entry in the
    source-controlled `forge/nvidia-runtime.approved` manifest.
11. A parseable RTX 4090 `nvidia-smi` record with matching VRAM capacity, enough currently
    available VRAM, and temperature headroom for the plan ceilings.

The checked-in probe plan hash is
`sha256:566b33b809d2051e5009cf0810f1a941a00b472ae2b55eb7ea8fc98821998754`. Run it
through the same launcher paths used above:

```powershell
.\scripts\run_model_forge.ps1 `
  -Mode Probe `
  -Plan .\forge\examples\gpt-oss-20b-4090-probe.plan.json `
  -BaseImage "python:3.12-slim@sha256:<verified-digest>" `
  -BaseModelDir D:\Collective\Models\GPT-OSS-20B `
  -DatasetDir D:\Collective\Datasets\Forge `
  -OutputDir D:\Collective\ProofVault\ModelForge `
  -AcceptPlanHash "sha256:566b33b809d2051e5009cf0810f1a941a00b472ae2b55eb7ea8fc98821998754"
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
- Constraint signals keep VRAM and host-RAM observations separate, identify their evidence source,
  and expose failed constraints without converting storage capacity into memory evidence.
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
