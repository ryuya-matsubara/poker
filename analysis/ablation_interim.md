# Jam model ablation: measured interim results

Source: e562b615480bbb83b419f7c08e24975a76feec4a; run 36677623500. Each model: 30M iterations, seed42, 10,000 accepted conditional EV samples per spot. Same hole-deal stream and first runout; changed action trees consume decision draws differently. Not a convergence certificate.

| Model | UTG open | HJ open | CO open | BTN open | SB raise (limp excluded) | BTN AQo jam | BTN A5s jam | BTN22 jam | 53s vs UTG jam |
|---|---|---|---|---|---|---|---|---|---|
| chance | 15.188% | 18.454% | 23.610% | 29.421% | 6.373% | 0.194% | 3.677% | 16.568% | 0.000% |
| full | 16.221% | 18.107% | 22.413% | 30.096% | 4.694% | 0.000% | 99.860% | 0.497% | 0.066% |
| legacy | 24.206% | 24.898% | 27.299% | 31.850% | 33.087% | 51.811% | 65.945% | 33.517% | 6.899% |
| nojam | 21.531% | 22.493% | 23.930% | 28.056% | 26.119% | 0.000% | 0.000% | 0.000% | 6.561% |
| raises | 16.282% | 18.387% | 22.754% | 32.937% | 33.893% | 1.155% | 76.613% | 0.372% | 0.408% |
| raw | 23.366% | 24.151% | 25.830% | 29.790% | 34.358% | 64.200% | 61.720% | 28.650% | 6.555% |
| rich | 12.244% | 12.959% | 14.091% | 18.957% | 1.904% | 97.540% | 83.755% | 30.459% | 1.950% |
| signed | 15.386% | 18.425% | 21.887% | 30.040% | 24.608% | 0.008% | 24.681% | 9.115% | 0.034% |
| sizes | 16.087% | 18.635% | 22.190% | 28.451% | 5.756% | 0.006% | 0.206% | 0.000% | 0.000% |

## What the numbers establish

Legacy AQo jam is 51.811%; removing clipping alone while retaining the coarse game and old average drops it to 3.007% in additional control run36675861053. For 53s, legacy jam6.899% has EV -4.593BB (SE0.225), versus clipping-only control jam0.00163%. Negative-evidence loss in stochastic clipped updates is a substantial contributor. This comparison is one seed, not an additive decomposition of all causes.

Rich features without postflop raises produce AQo jam97.540%, while rich features with bounded raises produce jam~0.000%. The no-raise game systematically changes the value of entering postflop. Richer private information alone is insufficient. Opponent strategies also change between models, so EV differences cannot be interpreted as a fixed per-hand bonus.

Full A5s remains jam99.860% at30M, despite jamEV -0.268BB (SE0.103), raise2BB +0.039BB (SE0.102), raise2.5BB +0.084BB (SE0.085). The paired jam-minus-raise2.5 gap is -0.352BB (SE0.096). This is evidence against declaring this checkpoint converged. With two boards/iteration, A5s jam falls to3.677% and raise2BB約96.3%; this is an experimental sensitivity result, not a frequency target.

The sizes variant (3bet5/7BB; 4betjam only) yields A5s jam0.206%, but AQo vs UTG retains an estimated one-step gain0.513BB. Removing 14BB4bet is not by itself a convergence fix.

30/60/120M three-seed full runs36677245310 are still running. Final release remains gated on their validation. A separate matched linear-regret weighting trial36697590869 tests algorithmic sensitivity without changing the game, features, chance stream, or average weighting. No frequencies are edited.

Artifacts store complete169-hand distributions and all actionEV/SE/CI; rawrun data remain in GitHub Actions. Interim results do not establish full6-player NLHE Nash convergence.


## Additional completed verification

Unchanged-game linear-weight trial run36697590869 succeeded, sourcec7dd8dd75235acb85e8c782e1eff1ac545561dc4, artifact11088464754. At30Mseed42:
- BTN AQo: Fold~0%, raise2BB95.09%, raise2.5BB3.31%, jam1.60%. EV1.7489/1.6268/1.8107BB for the non-fold actions.
- BTN A5s: Fold0.03%, raise2BB42.77%, raise2.5BB43.76%, jam13.44%. EV0.2616(SE0.0866)/0.2449(SE0.0933)/-0.1112(SE0.1076)BB. Jam advantage against the current average policy is -0.3153(SE0.0782)BB: still a statistically significant convergence warning.
- BTN22: jam10.07%, jam advantage-0.2882(SE0.1002)BB: another warning.
- 53s vsUTG2BB: Fold99.68%, Call0.16%, raise7BB0.04%, jam0.12%.
- AQo vsUTG2BB: Call75.31%, raise7BB7.47%, jam17.22%; raise advantage-0.5750(SE0.1677)BB.
The linear trial is not selected just because shove frequencies look better.

Independent update-kernel benchmark run36700084717 succeeded, sourcecd5f059a8d52d68dea5e27427039239dc398ae31:
- 200,000 external-sampling iterations on perfect-recall two-player Kuhn poker.
- Actual shared regret/average update function, exploration and reach corrections; chance RNG separated from cloned decision RNG.
- All64 pure contingent strategies per player enumerated to compute exact best responses.
- Learned game value-0.055581 vs theoretical -1/18=-0.055556.
- Exact two-player NashConv0.007888.
- 26Rust tests passed,2 upstream tests ignored; Python3export+4analysis tests passed.
This is a benchmark of the sampled kernel only. It does not certify the rich imperfect-recall six-player NLHE abstraction or establish its exploitability.
