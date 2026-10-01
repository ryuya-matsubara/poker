# CO TT local frozen-policy all-in diagnostic — 2026-10-01

User requested stopping GitHub Actions computation and calculating in ChatGPT. Remote diagnostic run 36851593526 is confirmed cancelled; its monitoring task is disabled. No new training or published strategy change occurred.

## Result

6-max, each player starts 20BB, SB0.5BB/BB1BB, no ante/rake. UTG folds, MP raises to2.5BB, CO holds TT and considers a20BB shove. Values are net BB from CO's decision, including loss of the20BB investment when beaten. Fold has exactly0BB EV.

| Saved training | CO average Fold / Call / Raise7BB / Jam (%) | Jam EV (BB) | SE (BB) | Individual95% MC CI | Samples | All opponents fold |
|---|---|---:|---:|---|---:|---:|
| seed42,80M | 0.0000084 /21.0503 /26.5583 /52.3914 |4.404390|0.021534|[4.362184,4.446596]|1,000,000|31.6406%|
| seed73,95M | 0.0000007 /29.4759 /44.6024 /25.9218 |3.128532|0.020423|[3.088503,3.168561]|1,000,000|36.4374%|
| seed101,84M | 0.0000093 /98.1774 /0.0122 /1.8104 |3.396933|0.021111|[3.355555,3.438311]|1,000,000|32.0900%|

Each1M diagnostic took7.339/8.230/8.313 seconds respectively (includes blueprint loading and10,000 evaluator tests), measured in the ChatGPT workspace. This is a small all-in evaluation and cannot be compared to the cost of jointly training an entire poker game.

A preliminary independent seed42 run (diagnostic RNG9127,200k accepted deals) found4.425839BB, SE0.048102, consistent with the1M run (RNG19027). Variation between saved models is about1.276BB, far larger than Monte Carlo error. These models were trained for different iteration counts, so this is not an equal-budget seed-stability test.

## What this proves and does not prove

Shoving TT is profitable relative to folding against all three frozen approximate opponent policies. A single TT shove is not shown to be an obvious mistake. The opponent's actual unseen KK from the screenshot is never used in constructing CO's decision; MP's entire conditional range is sampled.

This does NOT establish that52.39% is the GTO shove frequency. Call and raise7BB could have higher EV. Their values require postflop play; the compact61–65MB preflop blueprints do not contain the saved joint postflop policy. We did not replace that missing continuation with forced showdown or a guessed position coefficient. The GTO ranking/mixing frequencies remain unresolved. No strategy-frequency change is justified by this diagnostic alone.

## Method

- Read full binary preflop blueprint average strategies without browser export truncation or4-decimal rounding.
- Fix one TT suit combination;169-bucket suit-invariant policies and uniform remaining cards make its expectation suit-isomorphic to all TT combinations.
- Deal all other players' hole cards without replacement. Accept the deal with the saved probability of UTG fold and then MP actionindex2 (raise5halfBB=2.5BB). This conditions MP/UTG ranges on the observed actions while retaining blockers and folded dead cards.
- Set CO actionindex3 (all-in). BTN,SB,BB,then MP each choose between fold(index0) and all-in call(index1), using their own hand bucket and complete action history.
- All participating stacks become exactly20BB; no further betting is possible. Uniformly sample a five-card board from the same deck and determine exact best five-of-seven rank. Uncalled CO money is effectively returned by net-pot accounting; when all fold, CO gains4BB (MP2.5+SB0.5+BB1).
- Preserve all folded contributions; split ties equally; assert sum of all six terminal payoffs is0 on every accepted deal. No arbitrary terminal corrections.
- Refuse missing policy entries instead of inventing fallback ranges. None missing on the evaluated paths.
-10,000 random seven-card hands tested against enumeration of all21 five-card subsets; royal-flush/quads ordering and TTbucket8 assertions;3M payoff-conservation checks.
- Report individual95% normal Monte Carlo intervals. They quantify sampling error conditional on the frozen policy, not NLHE abstraction/convergence error.

Source `tools/co_tt_local.cpp`, results/provenance `analysis/co_tt_local_results.json`. Training source679913ade0d3a19e10573c5a9f7b7636d5bb2a3b, upstream4ade6a9e15a841c41867afde1258b9d110cd6fb1. ArtifactIDs and exact blueprintSHA256s are recorded in results.

## Reproduce

Compile `g++ -O3 -std=c++17 tools/co_tt_local.cpp -o co_tt_local`; this builds the compact evaluator. Run `./co_tt_local PATH/80m-blueprint.bin 1000000 19027`; arguments select the saved blueprint, number of conditionally accepted deals, and diagnostic RNG seed. Use95m/84m blueprint paths for the other models. All computations are local; no workflow or model learning is invoked.
