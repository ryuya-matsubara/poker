# 2026-09-30 training interruption and recovery

Run 36677245310 was cancelled at the configured 350 minute job deadline.
Preparation 36708598756 correctly refused to promote it. No main/Pages release
was performed. All three seeds retained 30M/60M chart, EV and preflop blueprint
artifacts. These are diagnostic evidence, not complete trainer checkpoints.

Seed42 completed 30M at 06:34 UTC and 60M at 06:55 UTC. The final log reports
39.9M iterations into the last 60M segment (99.9M cumulative), 2,037,177 preflop
and 304,062,496 postflop infosets. The state count and sharp slowdown are
consistent with memory pressure/swap thrashing; the log alone does not measure
page-fault rates, so this is an inference, not a proven profiler result.

Simply rerunning the 120M job or resuming only its preflop blueprint is invalid.
The latter loses all postflop regrets and averaging mass, and the deal RNG.

`add_resumable_solver.py` layers an operational extension on the immutable v7
game. It uses serializable ChaCha8 RNG, fixes traverser scheduling to cumulative
iteration, and streams a gzip checkpoint containing preflop blueprint, every
postflop key/regret/average entry and RNG state. Atomic rename prevents incomplete
files being accepted. A split-run regression requires bit-for-bit equality of
both preflop and postflop regrets/average mass and next RNG output, including a
split that is not divisible by six. A blueprint is rejected as resume input.

This changes chance trajectories; v8 must start from zero and its checkpoints
must never be mixed with v7 or exported as v7-trained evidence. The game tree,
utility, action sizes, 169 private identity, sampling/regret update and frequency
generation are unchanged. No action frequency is calibrated.

New Actions runs are split at 30/60/80/90/100/110/120M, with a complete state
uploaded after each successful segment, along with source hashes and numerical
evidence. The expensive end segments get separate job budgets. No publication
is triggered by this recovery workflow. Existing release gates remain required.
Memory growth is not solved by checkpointing; profiling/storage or a justified
abstraction change may still be necessary if later segments exceed resources.
Until actual runs/tests finish, this is recovery infrastructure, not evidence of
convergence or a successful deployment.
