# 保存済みv8戦略の実験版

2026-10-01、ユーザー指示で追加学習を停止。公開戦略は事前に主系列としたseed42の80Mをそのまま使用。seed73は95M、seed101は84M。頻度を編集・平均・補正していない。120M学習・収束確認は完了していない。GTO精度の証明ではない。

# 6-max 20BBプリフロップモデルの監査と修正

条件：全員20BB effective、SB0.5BB/BB1BB、ante0、rake0。旧mainは `51dc0a6d8ae656078bc221681f8e0681d6bc3f9f`。上流は `exinori/DCFR-SOLVER` の `4ade6a9e15a841c41867afde1258b9d110cd6fb1` に固定。名前からDCFRと推測せず `src/preflop.rs` と `src/infoset.rs` を読んだ。

## 原因と切り分け

1. 旧preflop/postflopはexternal samplingに毎訪問 `regret=max(0,regret+advantage)` を適用していた。DCFRの正負regret discountではない。CFR+のclippingは正確なfull-tree更新で有用だが、このstochastic更新では負の証拠を失い、不利なactionがサンプリングノイズで繰り返し復活する。旧平均戦略もown reachを掛けず、iteration×strategyを訪問時に加算していた。
2. 30M seed42の**clippingだけを取り除く対照実験**では、他のabstraction/averagingを維持して、BTN AQo jamが60.684%→7.262%、UTG2BBに対するBTN53s jamが5.953%→0.394%になった。53s旧jam EVは−4.442±0.227BB(SE)、新対照は約−3.60BB。それでも旧戦略に約6%残ることはnoise/clippingの問題を支持する。相手戦略も再学習されるためEVの変化を同じ相手に対するpure action差と解釈しない。
3. 粗いprivate abstractionにはKQと73が9-6-2 rainbowの同じHighCard bucketに入る例がある。rank/suited identity、kicker、overcard、nut blockerなどが失われる。旧モデルにpostflop raiseがなく、small-open branchだけがその不完全ゲームを通る。jam/call branchは実カードのshowdownへ進む。30M実験でrich/no-raiseはAQo約99%jam、rich/raisesは約9%jamになった。**情報だけ細かくしてもraise treeが不完全なら改善しない。** この旧public-key実験は追加圧縮前の値であり、最終のmatched9条件結果は後掲する。
4. raw showdownへ戻すとAQo jam約81%、53s jam約9%。raw equityに統一するだけではNLHE continuationの代わりにならない。固定tax/bonusは全条件0のまま。過去Q5oのtax問題は `tax_sensitivity.md` に保存し、今回の異常と分離した。
5. exactなpublic history/stack組合せを細かく保存すると30Mで約106M postflop infoset、最大RSS約13GB。4board/iteration条件はrunner shutdownで中断した。public-state集約だけでは約100M infosetが残り120M/4board条件はshutdownした。rank-band化も試したが30Mで約75M infosetが残った。最終モデルはprivate169を保持し、post entryを32bytesへ圧縮し、Actions runnerへ40GiB swapを用意した。bounded street/action/public abstractionは維持して、精度を削るよりdiskと時間を増やす方針で全9条件を再実行した。中断条件を成功として扱っていない。

## ソース変更

- `tools/continuation.rs`: signed external-sampling MCCFR、own reachを含む平均戦略、sampling importance correction、iteration内policy snapshot、shared runout、bounded postflop raise、より豊かなprivate/public key、凍結policy EV診断とproperty tests。
- `tools/continuation_legacy.rs`: 旧モデルを比較用に保存。実ゲームの手書きrangeに置換しない。
- `tools/patch_solver_base.py` / `tools/upgrade_solver.py` / `tools/patch_solver.py`: pinned upstreamへの再現可能patch、20BB/blind、short-all-in/reopening修正、30/60/120M checkpoint。
- `tools/export_preflop_policy.py`: importance-weighted massを「訪問回数」と誤認し浅い履歴を落とさないよう、全てのdepth≤4のsampled historyと正の平均戦略を保存。頻度は学習値の正規化のみ。
- `tools/analyze_jam.py`, `tools/promote_jam.py`: action EV/paired差/infoset delta/full169/seed/iterationレポート。
- `tools/validate_preflop.py`, `tools/test_preflop_export.py`, `tools/test_preflop_frontend.cjs`: collapse警告、確率/20BB/bucket/history/action order/浅い履歴coverageの回帰検証。
- 学習・ablation・finalize・Pages workflow: 学習データと実験証跡を保存し、検証してJSONを更新・公開。

## CFR/MCCFRの定義

相手actionを `q(a)=0.95π(a)+0.05/|A|` でsampleする。traverser actionは全列挙。sampled subtree値にはπ/qを掛ける。到達までのopponent/chance sampling補正をregretに適用し、own reachはregretへ掛けない。平均戦略には `linear_iteration_weight × own_reach / sampled_opponent_reach × π(a)` を加える。chanceは一様な重複なし6人hole dealとrunoutをsampleし、既知のchance sampling項が期待値で相殺する。戦略判断はown holeと現在のpublic boardを使う。他playerのhole cardや未来boardを渡さない。

累積regretはsignedで保存し、regret matchingでは正の部分だけを正規化する。全actionが非正ならuniform。sampling correctionのclip、固定bonus、hand-specific penaltyはない。branch間のcommon random numbers用にdecision RNGをcloneしても、次deal/runoutのstreamを巻き戻さないよう、deal・board・decision RNGをepisode seedで分離する。1board/2board、異なる戦略でもdeal streamを同一に保つ。各iterationでpolicyを凍結してから1人のtraverserを巡回更新し、同じinfosetの再訪問で更新途中のpolicyを使わない。checkpoint EV診断は学習RNG/runoutを復元して学習軌跡を変えない。

**多人数とimperfect recall**: 6人ゲームは、2人zero-sumのCFRと同じNash収束保証を持たない。さらに履歴とmoneyのabstractionはimperfect recallである。iteration/seed stabilityは抽象モデル内の安定性であり、NLHE全体のGTO誤差の証明ではない。

## Continuationとterminalの一貫性

全preflop terminalを同じjointモデルへ渡す。non-all-inはFlop/Turn/Riverの実際のfold/call/bet/raiseを通り、all-inは合法なfuture decisionが無いため同じrunout/payoffで精算する。jamへ人工的なbonusは与えない。ただしnon-all-inの近似誤差は残るため、raw/nojam/rich/raises/chance/sizesのablationで相対価値を確認する。

Postflop tree：check、33%pot、75%pot、all-in。bet facing：fold/call、3×またはmin-raiseを満たすraise、all-in。各street最大1raise。新規bet/raiseへの支払は累積street contributionとの差で計算する。short-all-inは未対応者のcallを要求するが既にactionした人のraise権を再開しない。side pot、fold payoff、all-in call、showdownは上流のchip conservation処理を使い、合法ランダムstate 10,000件のpreflop＋postflopで `sum(payoff)≈0`, stacks≥0, stack+contribution=20BBを検証する。

Preflop/Postflopとも169 rank/suited identityを保持し、private keyはboard-relative made/draw、hole high/low rank、overcards、flush/backdoor count、straight potential、A/K nut/near-nut blockerを保持する。made classifierはtop/non-top pair、overpair/underpair、kickerの粗い強度を区別する。middle/bottom pair、gutshot/open-ended/double-gutshotの全種類は完全には分離せず、hole ranks・board bins・straight potentialとの組合せで近似する。完全な1326 suit-labelled identity、全backdoor種類、正確なrange-relative equity/nut advantageは保持しない。nut blockerはboard suitに対するprivate featureであり、相手rangeに対する完全なnut advantageではない。

Public keyはboard rank/texture、position/actor、active/folded/all-in masks、preflop pot type(first/last aggressor, raise count)、street bettor/raise/acted/pending state、直前2streetのaggressor summaries、pot bucket、各active opponentのstack band、SPR、to-call由来pot odds16段階、bet/pot比を持つ。pot bandsはhalfBB chipsで3/6/10/16/24/40/64/96/160/240、stack bandsは0/4/10/20/40、SPRは0/0.5/1/2/4/8。正確なbet合法性/stack/side pot/payoffはbucket化しない。exact action sequence全体は保持せず戦略上のbetting stateへ集約する。random hash collision、memory eviction、固定realization係数は用いない。

## 方式の比較と選択

| 方式 | 精度と要件 | 計算量・Actions実行 | 判断 |
|---|---|---|---|
| Preflop CFR + 高精度leaf oracle | range-conditioned HU/multiway continuation oracleを別に学習/solveする必要。両者のactual holeをoracle policyへ見せると情報漏洩 | 全pot type/position/stack/rangeに対するoracleの再solve/cachingとrange整合が必要。既存repoにoracleなし | 今回のresource/既存codeでは適切なoracleの構築までできず不採用 |
| Representative flop subgame | texture/isomorphism、blockerとboard条件付きrange、rare nut textureを重み付け。単一HUの局所solveは精密でも6-wayにそのまま移せない | 条件付きrangeが学習中に変化し、多数のre-solvingとturn/river treeが必要。実装費/実行時間を事前に固定できない | 将来の改善候補。実測solver結果を生成したと主張しない |
| Joint bounded CFR（採用） | private/public abstractionを改善し、実際のstreet bet/call/fold/raiseを共通木で学習。6人を扱える | 30M各条件/120M3seedで実測。明示的state aggregationとcompact entriesでActions制限へ収める | 現repositoryで実行可能。full NLHE精度保証は無い |

A/Bの時間は実装して実測したものではない。Cのruntime/RSSとablationは各 `training.log` にある。HU exact solverを全terminalへ呼び出した、あるいは均衡済みoracleを搭載したという報告ではない。

## Preflop action tree

open2/2.5BB（SB3BB）、3bet7BB、4bet14BB、all-inをbaselineとする。追加ablation `sizes` は3bet5/7BB・4betjamのみ。14BBで6BBを残すactionは合法で、誘発/価格付けがjamとは異なるため「無意味」と決めつけて削除しない。5/7BBをIP/OOP別に精密最適化したとの主張はしない。action setがrangeとEVへ与える差を実測して記録し、再現できる代表sizeとしてbaselineを保つ。ベットサイズの連続空間は未solve。

## 外部benchmarkと限界

- [GTO Wizard: Why Not Shove?](https://blog.gtowizard.com/why-not-shove/): 20BBで5BB程度の3betを含む説明。exact6-max/noante/norakeのfull169 benchmarkではない。
- [GTO Wizard: When to Open Shove](https://blog.gtowizard.com/when-to-open-shove-vs-different-player-profiles/): BTN20BB例は**1BB total ante**、chipEV。noanteの正解頻度として強制しない。
- [HRC tree configuration](https://www.holdemresources.net/docs/tree-config/) と [postflop calculations](https://www.holdemresources.net/docs/postflop/): postflop abstractionとbet sizesがpreflopへ影響する。これらは手順/モデルの一次資料で、同条件のpublic169解ではない。
- [OpenSpiel external sampling](https://github.com/google-deepmind/open_spiel/blob/master/open_spiel/python/algorithms/external_sampling_mccfr.py): simple averageとfull average、multi-playerでの制約をコードと比較。
- [CFR+論文](https://arxiv.org/abs/1407.5042)、[Local Best Response](https://arxiv.org/abs/1612.07547): full-game BR/NashConvは未計算。局所EV評価のmax mean action−policy meanはone-step deviation検査で、全streetで最適反応するBRではない。

外部条件の記録（2026-09-30確認）:

| 公開資料 | 人数/stack | ante | rake | open size | 用途 |
|---|---|---|---|---|---|
| GTO Wizard BTN20BB記事 | BTN/SB/BB局所・20BB chipEV、完全6max range無し | total1BB | 記事はchipEV | minraise/jam | shove/rangeの方向のみ。noanteの正解ではない |
| MonkerGuy 6max NLH noante pack | 6max・20〜200BB | 0 | 5% | public listingでは全size不明 | 同条件ではない。公開169頻度無し、有料購入していない |
| HRC公式手順 | configurable cash/MTT | configurable | configurable | tree設定 | モデル設計の資料。今回のsolve/基準表は取得していない |
| Simple Preflop Holdem公式 | configurable multiway | configurable | configurable | tree設定 | postflop abstractionとsampling方式の確認。今回のsolve/基準表無し |

[MonkerGuy public listing](https://www.monkerguy.com/) は6max/noanteでもrake5%なので、今回のrake0戦略へ一致を求めない。[Simple Preflop Holdem](https://simplepoker.com/en/Solutions/Simple_Preflop_Holdem) はcard abstraction/Monte Carloを使うsolverだが、その商用結果を今回生成したと主張しない。

同一条件の公認GTOチャートを取得できなかったので、絶対的なGTO距離、GTO Wizard相当、何%GTOという数値は提示しない。premium/weak、suited/offsuit、position、action EV、全169レンジ、複数seed/iterationの内部validationを行う。境界handの一致を収束の証明として使わない。ゲーム中のpostflop CPUはこれらtraining postflop policyを参照せず既存の簡易decisionを使うため、**CPU全体がGTOであるという主張はできない。**

EV診断の注意：同じデータで最大mean actionを選ぶためone-step gainはsampling noiseで上振れし得る。95%警告は探索的で多重比較補正はしていない。到達しにくいoff-policy postflop infosetの平均戦略は未学習ならuniformとなり、forced action EVは最適なpostflop continuation EVではない。この不確実性もfull-game GTO誤差とは区別する。


## 旧mainと公開snapshot・action EV

| spot | hand | action | old | snapshot | EV BB | SE BB | N |
|---|---|---|---|---|---|---|---|
| BTN RFI | AQo | fold | 0.272% | 0.000% | 0.00000 | 0.00000 | 10000 |
| BTN RFI | AQo | raise 4 | 13.349% | 99.985% | 1.60332 | 0.10695 | 10000 |
| BTN RFI | AQo | raise 5 | 25.218% | 0.013% | 1.54662 | 0.10439 | 10000 |
| BTN RFI | AQo | allin | 61.160% | 0.002% | 1.59940 | 0.09913 | 10000 |
| BTN RFI | AA | fold | 0.055% | 0.000% | 0.00000 | 0.00000 | 10000 |
| BTN RFI | AA | raise 4 | 61.487% | 73.403% | 5.10275 | 0.10124 | 10000 |
| BTN RFI | AA | raise 5 | 35.945% | 26.595% | 5.02797 | 0.09953 | 10000 |
| BTN RFI | AA | allin | 2.514% | 0.002% | 4.37140 | 0.09023 | 10000 |
| BTN RFI | A5s | fold | 3.249% | 0.000% | 0.00000 | 0.00000 | 10000 |
| BTN RFI | A5s | raise 4 | 17.258% | 93.841% | 0.34260 | 0.08704 | 10000 |
| BTN RFI | A5s | raise 5 | 13.782% | 5.011% | 0.30965 | 0.08913 | 10000 |
| BTN RFI | A5s | allin | 65.712% | 1.149% | 0.14353 | 0.10031 | 10000 |
| BTN RFI | 22 | fold | 76.601% | 2.945% | 0.00000 | 0.00000 | 10000 |
| BTN RFI | 22 | raise 4 | 2.463% | 82.730% | 0.01622 | 0.08421 | 10000 |
| BTN RFI | 22 | raise 5 | 3.538% | 2.094% | -0.25630 | 0.09231 | 10000 |
| BTN RFI | 22 | allin | 17.398% | 12.231% | -0.16933 | 0.11376 | 10000 |
| BTN RFI | Q5o | fold | 96.174% | 99.998% | 0.00000 | 0.00000 | 10000 |
| BTN RFI | Q5o | raise 4 | 0.916% | 0.001% | -1.15888 | 0.09681 | 10000 |
| BTN RFI | Q5o | raise 5 | 0.866% | 0.001% | -0.87613 | 0.08679 | 10000 |
| BTN RFI | Q5o | allin | 2.044% | 0.000% | -1.27468 | 0.10702 | 10000 |
| UTG 2BB -> BTN | 53s | fold | 88.900% | 99.974% | 0.00000 | 0.00000 | 10000 |
| UTG 2BB -> BTN | 53s | call | 3.520% | 0.000% | -2.84334 | 0.15483 | 10000 |
| UTG 2BB -> BTN | 53s | raise 14 | 2.730% | 0.000% | -3.10965 | 0.14121 | 10000 |
| UTG 2BB -> BTN | 53s | allin | 4.850% | 0.026% | -1.81844 | 0.16079 | 10000 |
| UTG 2BB -> BTN | AQo | fold | 0.910% | 0.000% | 0.00000 | 0.00000 | 10000 |
| UTG 2BB -> BTN | AQo | call | 9.560% | 74.857% | 1.99037 | 0.17954 | 10000 |
| UTG 2BB -> BTN | AQo | raise 14 | 48.930% | 22.857% | 0.88782 | 0.17322 | 10000 |
| UTG 2BB -> BTN | AQo | allin | 40.590% | 2.286% | 1.71185 | 0.15038 | 10000 |

## 複数seed・iteration比較（異なる最終iteration）

{
  "42:60-80": {
    "UTG RFI": {
      "combo_weighted_rms": 0.022822835858771418,
      "total_open_difference": 0.001970078350699539
    },
    "HJ RFI": {
      "combo_weighted_rms": 0.03485163883472863,
      "total_open_difference": 0.0010540354258002094
    },
    "CO RFI": {
      "combo_weighted_rms": 0.035460618270776456,
      "total_open_difference": 0.004021986648285236
    },
    "BTN RFI": {
      "combo_weighted_rms": 0.023459971805544207,
      "total_open_difference": 0.002579822365119333
    },
    "SB RFI": {
      "combo_weighted_rms": 0.06514188253487745,
      "total_open_difference": 0.011116211322677635
    }
  },
  "73:60-95": {
    "UTG RFI": {
      "combo_weighted_rms": 0.02864705258653176,
      "total_open_difference": 0.0005587477128507212
    },
    "HJ RFI": {
      "combo_weighted_rms": 0.07341108845704562,
      "total_open_difference": 0.01206177109492601
    },
    "CO RFI": {
      "combo_weighted_rms": 0.04388867300930735,
      "total_open_difference": 0.001883032606571633
    },
    "BTN RFI": {
      "combo_weighted_rms": 0.03165243102579278,
      "total_open_difference": 0.0008675611108119874
    },
    "SB RFI": {
      "combo_weighted_rms": 0.1199416734805114,
      "total_open_difference": 0.028044099502870345
    }
  },
  "101:60-84": {
    "UTG RFI": {
      "combo_weighted_rms": 0.032718041508981166,
      "total_open_difference": 0.0024838641978250087
    },
    "HJ RFI": {
      "combo_weighted_rms": 0.041774963455022775,
      "total_open_difference": 0.005108092544200082
    },
    "CO RFI": {
      "combo_weighted_rms": 0.041970243588282184,
      "total_open_difference": 0.007446118897059428
    },
    "BTN RFI": {
      "combo_weighted_rms": 0.06111911070497137,
      "total_open_difference": 0.005660386171116916
    },
    "SB RFI": {
      "combo_weighted_rms": 0.09845891697453865,
      "total_open_difference": 0.026470677238180765
    }
  },
  "42-vs-73": {
    "failed": "different seeds AND unequal iterations: SB RFI unstable: RMS=0.225, total=0.025"
  },
  "42-vs-101": {
    "failed": "different seeds AND unequal iterations: SB RFI unstable: RMS=0.182, total=0.020"
  }
}

## 同時区間によるEV診断

{
  "ready": false,
  "comparisons": 84,
  "familywise_alpha": 0.05,
  "z": 3.433774986768099,
  "tolerance_bb": 0.05,
  "failures": [
    {
      "checkpoint": "seed42-80m",
      "spot": "UTG 2BB -> BTN",
      "hand": "AQo",
      "action": "call",
      "probability": 0.7485697269439697,
      "advantage_bb": 0.2583806968338537,
      "se_bb": 0.042969224596331033,
      "simultaneous_ci_bb": [
        0.1108340482141516,
        0.40592734545355574
      ]
    },
    {
      "checkpoint": "seed42-80m",
      "spot": "UTG 2BB -> BTN",
      "hand": "AQo",
      "action": "raise 14",
      "probability": 0.22857441008090973,
      "advantage_bb": -0.8441693027846766,
      "se_bb": 0.13411254081389984,
      "simultaneous_ci_bb": [
        -1.3046815908433618,
        -0.38365701472599156
      ]
    }
  ]
}

## 全seedのEV・警告

{
  "seed42-80m": [
    {
      "spot": "BTN RFI",
      "hand": "AQo",
      "policy_ev_bb": 1.603316817338111,
      "best_fixed_action": "raise 4",
      "one_step_deviation_gain_bb": 8.182661888955778e-06,
      "jam_minus_best_small_bb": -0.003924999999999956,
      "paired_se_bb": 0.0920378111446895,
      "warnings": [],
      "actions": [
        {
          "action": "fold",
          "ci95_bb": [
            0.0,
            0.0
          ],
          "estimated_regret_bb": -1.6033168173383558,
          "jam_difference_se_bb": 0.0991259467008055,
          "jam_minus_action_bb": 1.5994,
          "mean_bb": 0.0,
          "probability": 5.132865226187278e-07,
          "regret_se_bb": 0.10694430605993444,
          "samples": 10000,
          "se_bb": 0.0,
          "stored_cumulative_regret_half_bb": -250361.015625,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "raise 4",
          "ci95_bb": [
            1.3937021124639082,
            1.8129478875360916
          ],
          "estimated_regret_bb": 8.182661889077281e-06,
          "jam_difference_se_bb": 0.0920378111446895,
          "jam_minus_action_bb": -0.003925,
          "mean_bb": 1.603325,
          "probability": 0.9998505711555481,
          "regret_se_bb": 1.2524178880676445e-05,
          "samples": 10000,
          "se_bb": 0.10695045282453663,
          "stored_cumulative_regret_half_bb": 866.8133544921875,
          "current_regret_matching_probability": 1.0
        },
        {
          "action": "raise 5",
          "ci95_bb": [
            1.342027387160809,
            1.7512226128391908
          ],
          "estimated_regret_bb": -0.05669181733811092,
          "jam_difference_se_bb": 0.08766373593452026,
          "jam_minus_action_bb": 0.052775,
          "mean_bb": 1.546625,
          "probability": 0.0001261397555936128,
          "regret_se_bb": 0.0892131451587562,
          "samples": 10000,
          "se_bb": 0.1043865371628525,
          "stored_cumulative_regret_half_bb": -123.61752319335938,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "allin",
          "ci95_bb": [
            1.405113144466421,
            1.7936868555335788
          ],
          "estimated_regret_bb": -0.0039168173381109225,
          "jam_difference_se_bb": 0.0,
          "jam_minus_action_bb": 0.0,
          "mean_bb": 1.5994,
          "probability": 2.2701913621858694e-05,
          "regret_se_bb": 0.09202969591191686,
          "samples": 10000,
          "se_bb": 0.0991259467008055,
          "stored_cumulative_regret_half_bb": -17699.392578125,
          "current_regret_matching_probability": 0.0
        }
      ]
    },
    {
      "spot": "BTN RFI",
      "hand": "AA",
      "policy_ev_bb": 5.082851605752703,
      "best_fixed_action": "raise 4",
      "one_step_deviation_gain_bb": 0.019898394247297446,
      "jam_minus_best_small_bb": -0.73135,
      "paired_se_bb": 0.08613798345079421,
      "warnings": [],
      "actions": [
        {
          "action": "fold",
          "ci95_bb": [
            0.0,
            0.0
          ],
          "estimated_regret_bb": -5.082851605752118,
          "jam_difference_se_bb": 0.09022564225680006,
          "jam_minus_action_bb": 4.3714,
          "mean_bb": 0.0,
          "probability": 8.00996047267688e-10,
          "regret_se_bb": 0.09375413904596881,
          "samples": 10000,
          "se_bb": 0.0,
          "stored_cumulative_regret_half_bb": -394221.4375,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "raise 4",
          "ci95_bb": [
            4.904317757266402,
            5.301182242733598
          ],
          "estimated_regret_bb": 0.01989839424729762,
          "jam_difference_se_bb": 0.08613798345079421,
          "jam_minus_action_bb": -0.73135,
          "mean_bb": 5.10275,
          "probability": 0.7340326309204102,
          "regret_se_bb": 0.02226546628227852,
          "samples": 10000,
          "se_bb": 0.10124094017020314,
          "stored_cumulative_regret_half_bb": 2245.155029296875,
          "current_regret_matching_probability": 1.0
        },
        {
          "action": "raise 5",
          "ci95_bb": [
            4.832903232676831,
            5.223046767323169
          ],
          "estimated_regret_bb": -0.05487660575270238,
          "jam_difference_se_bb": 0.0817145521234766,
          "jam_minus_action_bb": -0.656575,
          "mean_bb": 5.027975,
          "probability": 0.2659515142440796,
          "regret_se_bb": 0.06145179513788064,
          "samples": 10000,
          "se_bb": 0.09952641189957599,
          "stored_cumulative_regret_half_bb": -1297.9635009765625,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "allin",
          "ci95_bb": [
            4.194557741176673,
            4.548242258823328
          ],
          "estimated_regret_bb": -0.7114516057527026,
          "jam_difference_se_bb": 0.0,
          "jam_minus_action_bb": 0.0,
          "mean_bb": 4.3714,
          "probability": 1.579207855684217e-05,
          "regret_se_bb": 0.07651052884900189,
          "samples": 10000,
          "se_bb": 0.09022564225680006,
          "stored_cumulative_regret_half_bb": -53787.6171875,
          "current_regret_matching_probability": 0.0
        }
      ]
    },
    {
      "spot": "BTN RFI",
      "hand": "A5s",
      "policy_ev_bb": 0.33866238770487256,
      "best_fixed_action": "raise 4",
      "one_step_deviation_gain_bb": 0.003937612295127457,
      "jam_minus_best_small_bb": -0.199075,
      "paired_se_bb": 0.095311350136193,
      "warnings": [],
      "actions": [
        {
          "action": "fold",
          "ci95_bb": [
            0.0,
            0.0
          ],
          "estimated_regret_bb": -0.3386623877048725,
          "jam_difference_se_bb": 0.10030923126325494,
          "jam_minus_action_bb": 0.143525,
          "mean_bb": 0.0,
          "probability": 1.0572116337925763e-07,
          "regret_se_bb": 0.08462832301392094,
          "samples": 10000,
          "se_bb": 0.0,
          "stored_cumulative_regret_half_bb": -9239.625,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "raise 4",
          "ci95_bb": [
            0.17199426946398438,
            0.5132057305360156
          ],
          "estimated_regret_bb": 0.003937612295127474,
          "jam_difference_se_bb": 0.095311350136193,
          "jam_minus_action_bb": -0.199075,
          "mean_bb": 0.3426,
          "probability": 0.9384074211120605,
          "regret_se_bb": 0.004979554083664717,
          "samples": 10000,
          "se_bb": 0.08704374006939573,
          "stored_cumulative_regret_half_bb": 1245.8519287109375,
          "current_regret_matching_probability": 0.5816317767085231
        },
        {
          "action": "raise 5",
          "ci95_bb": [
            0.13495820527003852,
            0.4843417947299614
          ],
          "estimated_regret_bb": -0.029012387704872526,
          "jam_difference_se_bb": 0.0947139202868676,
          "jam_minus_action_bb": -0.166125,
          "mean_bb": 0.30965,
          "probability": 0.050106536597013474,
          "regret_se_bb": 0.08244255111780933,
          "samples": 10000,
          "se_bb": 0.08912846669895994,
          "stored_cumulative_regret_half_bb": 896.142333984375,
          "current_regret_matching_probability": 0.41836822329147694
        },
        {
          "action": "allin",
          "ci95_bb": [
            -0.05308109327597968,
            0.3401310932759797
          ],
          "estimated_regret_bb": -0.19513738770487252,
          "jam_difference_se_bb": 0.0,
          "jam_minus_action_bb": 0.0,
          "mean_bb": 0.143525,
          "probability": 0.011485916562378407,
          "regret_se_bb": 0.0922638420217346,
          "samples": 10000,
          "se_bb": 0.10030923126325494,
          "stored_cumulative_regret_half_bb": -5903.48974609375,
          "current_regret_matching_probability": 0.0
        }
      ]
    },
    {
      "spot": "BTN RFI",
      "hand": "22",
      "policy_ev_bb": -0.012653660843893886,
      "best_fixed_action": "raise 4",
      "one_step_deviation_gain_bb": 0.028878660843893886,
      "jam_minus_best_small_bb": -0.18555,
      "paired_se_bb": 0.1096917344078839,
      "warnings": [],
      "actions": [
        {
          "action": "fold",
          "ci95_bb": [
            0.0,
            0.0
          ],
          "estimated_regret_bb": 0.012653660843893886,
          "jam_difference_se_bb": 0.11375793429998243,
          "jam_minus_action_bb": -0.169325,
          "mean_bb": 0.0,
          "probability": 0.02945154346525669,
          "regret_se_bb": 0.07742927460400542,
          "samples": 10000,
          "se_bb": 0.0,
          "stored_cumulative_regret_half_bb": -1538.006103515625,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "raise 4",
          "ci95_bb": [
            -0.14883037477560107,
            0.18128037477560105
          ],
          "estimated_regret_bb": 0.028878660843893886,
          "jam_difference_se_bb": 0.1096917344078839,
          "jam_minus_action_bb": -0.18555,
          "mean_bb": 0.016225,
          "probability": 0.8272987604141235,
          "regret_se_bb": 0.015570737383341325,
          "samples": 10000,
          "se_bb": 0.08421192590591892,
          "stored_cumulative_regret_half_bb": 2371.38818359375,
          "current_regret_matching_probability": 1.0
        },
        {
          "action": "raise 5",
          "ci95_bb": [
            -0.43722289687640703,
            -0.07537710312359294
          ],
          "estimated_regret_bb": -0.24364633915610612,
          "jam_difference_se_bb": 0.10742143336584249,
          "jam_minus_action_bb": 0.086975,
          "mean_bb": -0.2563,
          "probability": 0.020935118198394775,
          "regret_se_bb": 0.08788876467153495,
          "samples": 10000,
          "se_bb": 0.09230760044714645,
          "stored_cumulative_regret_half_bb": -972.5982666015625,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "allin",
          "ci95_bb": [
            -0.3922905512279656,
            0.05364055122796557
          ],
          "estimated_regret_bb": -0.15667133915610612,
          "jam_difference_se_bb": 0.0,
          "jam_minus_action_bb": 0.0,
          "mean_bb": -0.169325,
          "probability": 0.12231455743312836,
          "regret_se_bb": 0.09457344569051415,
          "samples": 10000,
          "se_bb": 0.11375793429998243,
          "stored_cumulative_regret_half_bb": -5085.5068359375,
          "current_regret_matching_probability": 0.0
        }
      ]
    },
    {
      "spot": "BTN RFI",
      "hand": "Q5o",
      "policy_ev_bb": -2.5054688658411808e-05,
      "best_fixed_action": "fold",
      "one_step_deviation_gain_bb": 2.5054688658411808e-05,
      "jam_minus_best_small_bb": -0.39854999999999996,
      "paired_se_bb": 0.09890816610514133,
      "warnings": [],
      "actions": [
        {
          "action": "fold",
          "ci95_bb": [
            0.0,
            0.0
          ],
          "estimated_regret_bb": 2.5054688658411805e-05,
          "jam_difference_se_bb": 0.10701821704418099,
          "jam_minus_action_bb": -1.274675,
          "mean_bb": 0.0,
          "probability": 0.9999751448631287,
          "regret_se_bb": 1.9342622247466308e-06,
          "samples": 10000,
          "se_bb": 0.0,
          "stored_cumulative_regret_half_bb": 423.88787841796875,
          "current_regret_matching_probability": 1.0
        },
        {
          "action": "raise 4",
          "ci95_bb": [
            -1.3486140462581833,
            -0.9691359537418168
          ],
          "estimated_regret_bb": -1.1588499453113241,
          "jam_difference_se_bb": 0.09963035635182019,
          "jam_minus_action_bb": -0.1158,
          "mean_bb": -1.158875,
          "probability": 8.789750609139446e-06,
          "regret_se_bb": 0.09680405568746946,
          "samples": 10000,
          "se_bb": 0.09680563584601186,
          "stored_cumulative_regret_half_bb": -22022.22265625,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "raise 5",
          "ci95_bb": [
            -1.0462240016162134,
            -0.7060259983837867
          ],
          "estimated_regret_bb": -0.8760999453113881,
          "jam_difference_se_bb": 0.09890816610514133,
          "jam_minus_action_bb": -0.39855,
          "mean_bb": -0.876125,
          "probability": 1.3901047168474179e-05,
          "regret_se_bb": 0.08678345605062598,
          "samples": 10000,
          "se_bb": 0.08678520490623134,
          "stored_cumulative_regret_half_bb": -18354.83203125,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "allin",
          "ci95_bb": [
            -1.4844307054065948,
            -1.0649192945934052
          ],
          "estimated_regret_bb": -1.2746499453113074,
          "jam_difference_se_bb": 0.0,
          "jam_minus_action_bb": 0.0,
          "mean_bb": -1.274675,
          "probability": 2.109880142597831e-06,
          "regret_se_bb": 0.10701694608695671,
          "samples": 10000,
          "se_bb": 0.10701821704418099,
          "stored_cumulative_regret_half_bb": -144189.6875,
          "current_regret_matching_probability": 0.0
        }
      ]
    },
    {
      "spot": "UTG 2BB -> BTN",
      "hand": "53s",
      "policy_ev_bb": -0.000483648394336364,
      "best_fixed_action": "fold",
      "one_step_deviation_gain_bb": 0.000483648394336364,
      "jam_minus_best_small_bb": 1.2912083333969113,
      "paired_se_bb": 0.15622673948688506,
      "warnings": [],
      "actions": [
        {
          "action": "fold",
          "ci95_bb": [
            0.0,
            0.0
          ],
          "estimated_regret_bb": 0.000483648394336364,
          "jam_difference_se_bb": 0.1607934722197527,
          "jam_minus_action_bb": -1.8184416666030885,
          "mean_bb": 0.0,
          "probability": 0.9997367858886719,
          "regret_se_bb": 4.1882681259532134e-05,
          "samples": 10000,
          "se_bb": 0.0,
          "stored_cumulative_regret_half_bb": 324.76959228515625,
          "current_regret_matching_probability": 1.0
        },
        {
          "action": "call",
          "ci95_bb": [
            -3.146814943845448,
            -2.539868389360729
          ],
          "estimated_regret_bb": -2.842858018208799,
          "jam_difference_se_bb": 0.1673073978348971,
          "jam_minus_action_bb": 1.0249,
          "mean_bb": -2.8433416666030884,
          "probability": 4.8116066864167806e-06,
          "regret_se_bb": 0.1548143414944437,
          "samples": 10000,
          "se_bb": 0.15483330471548973,
          "stored_cumulative_regret_half_bb": -13568.9453125,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "raise 14",
          "ci95_bb": [
            -3.386421584404572,
            -2.8328784155954274
          ],
          "estimated_regret_bb": -3.1091663516057086,
          "jam_difference_se_bb": 0.15622673948688506,
          "jam_minus_action_bb": 1.2912083333969115,
          "mean_bb": -3.10965,
          "probability": 2.7286585435604138e-08,
          "regret_se_bb": 0.14119008151177045,
          "samples": 10000,
          "se_bb": 0.1412099920431493,
          "stored_cumulative_regret_half_bb": -17283.28125,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "allin",
          "ci95_bb": [
            -2.1335968721538037,
            -1.5032864610523733
          ],
          "estimated_regret_bb": -1.817958018208792,
          "jam_difference_se_bb": 0.0,
          "jam_minus_action_bb": 0.0,
          "mean_bb": -1.8184416666030885,
          "probability": 0.00025839844602160156,
          "regret_se_bb": 0.16075159490934124,
          "samples": 10000,
          "se_bb": 0.1607934722197527,
          "stored_cumulative_regret_half_bb": -12731.794921875,
          "current_regret_matching_probability": 0.0
        }
      ]
    },
    {
      "spot": "UTG 2BB -> BTN",
      "hand": "AQo",
      "policy_ev_bb": 1.731985969387765,
      "best_fixed_action": "call",
      "one_step_deviation_gain_bb": 0.25838069683385356,
      "jam_minus_best_small_bb": 0.8240333335876465,
      "paired_se_bb": 0.14951513308939146,
      "warnings": [],
      "actions": [
        {
          "action": "fold",
          "ci95_bb": [
            0.0,
            0.0
          ],
          "estimated_regret_bb": -1.731985969387765,
          "jam_difference_se_bb": 0.1503827976112777,
          "jam_minus_action_bb": 1.7118500001907349,
          "mean_bb": 0.0,
          "probability": 8.669847773035144e-08,
          "regret_se_bb": 0.15982563082711543,
          "samples": 10000,
          "se_bb": 0.0,
          "stored_cumulative_regret_half_bb": -31561.537109375,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "call",
          "ci95_bb": [
            1.6384632208451257,
            2.3422701115981113
          ],
          "estimated_regret_bb": 0.2583806968338537,
          "jam_difference_se_bb": 0.16883592689266216,
          "jam_minus_action_bb": -0.27851666603088376,
          "mean_bb": 1.9903666662216186,
          "probability": 0.7485697269439697,
          "regret_se_bb": 0.042969224596331033,
          "samples": 10000,
          "se_bb": 0.17954257417168004,
          "stored_cumulative_regret_half_bb": 1544.5361328125,
          "current_regret_matching_probability": 1.0
        },
        {
          "action": "raise 14",
          "ci95_bb": [
            0.5483071019839518,
            1.2273262312222248
          ],
          "estimated_regret_bb": -0.8441693027846766,
          "jam_difference_se_bb": 0.14951513308939146,
          "jam_minus_action_bb": 0.8240333335876465,
          "mean_bb": 0.8878166666030883,
          "probability": 0.22857441008090973,
          "regret_se_bb": 0.13411254081389984,
          "samples": 10000,
          "se_bb": 0.17321916562200843,
          "stored_cumulative_regret_half_bb": -985.9678344726562,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "allin",
          "ci95_bb": [
            1.4170997168726305,
            2.0066002835088392
          ],
          "estimated_regret_bb": -0.02013596919703016,
          "jam_difference_se_bb": 0.0,
          "jam_minus_action_bb": 0.0,
          "mean_bb": 1.7118500001907349,
          "probability": 0.022855721414089203,
          "regret_se_bb": 0.143131394688866,
          "samples": 10000,
          "se_bb": 0.1503827976112777,
          "stored_cumulative_regret_half_bb": -3039.492431640625,
          "current_regret_matching_probability": 0.0
        }
      ]
    }
  ],
  "seed73-95m": [
    {
      "spot": "BTN RFI",
      "hand": "AQo",
      "policy_ev_bb": 1.580788855005475,
      "best_fixed_action": "raise 4",
      "one_step_deviation_gain_bb": 0.11446114499452498,
      "jam_minus_best_small_bb": -0.10929999999999995,
      "paired_se_bb": 0.08920652235886756,
      "warnings": [],
      "actions": [
        {
          "action": "fold",
          "ci95_bb": [
            0.0,
            0.0
          ],
          "estimated_regret_bb": -1.5807888550054747,
          "jam_difference_se_bb": 0.0953823282301489,
          "jam_minus_action_bb": 1.58595,
          "mean_bb": 0.0,
          "probability": 2.4978611179449217e-08,
          "regret_se_bb": 0.10055210028458003,
          "samples": 10000,
          "se_bb": 0.0,
          "stored_cumulative_regret_half_bb": -297951.3125,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "raise 4",
          "ci95_bb": [
            1.4851526683575769,
            1.905347331642423
          ],
          "estimated_regret_bb": 0.11446114499452524,
          "jam_difference_se_bb": 0.08920652235886756,
          "jam_minus_action_bb": -0.1093,
          "mean_bb": 1.69525,
          "probability": 0.26448407769203186,
          "regret_se_bb": 0.06397102589102735,
          "samples": 10000,
          "se_bb": 0.10719251614409343,
          "stored_cumulative_regret_half_bb": 655.2230224609375,
          "current_regret_matching_probability": 0.3190917763817297
        },
        {
          "action": "raise 5",
          "ci95_bb": [
            1.3283775584487858,
            1.7508724415512142
          ],
          "estimated_regret_bb": -0.04116385500547476,
          "jam_difference_se_bb": 0.08528169980288636,
          "jam_minus_action_bb": 0.046325,
          "mean_bb": 1.539625,
          "probability": 0.7354398965835571,
          "regret_se_bb": 0.02300742204613269,
          "samples": 10000,
          "se_bb": 0.10777930691388483,
          "stored_cumulative_regret_half_bb": 1398.1768798828125,
          "current_regret_matching_probability": 0.6809082236182703
        },
        {
          "action": "allin",
          "ci95_bb": [
            1.399000636668908,
            1.7728993633310919
          ],
          "estimated_regret_bb": 0.0051611449945252385,
          "jam_difference_se_bb": 0.0,
          "jam_minus_action_bb": 0.0,
          "mean_bb": 1.58595,
          "probability": 7.602479308843613e-05,
          "regret_se_bb": 0.07733979398556273,
          "samples": 10000,
          "se_bb": 0.0953823282301489,
          "stored_cumulative_regret_half_bb": -14962.845703125,
          "current_regret_matching_probability": 0.0
        }
      ]
    },
    {
      "spot": "BTN RFI",
      "hand": "AA",
      "policy_ev_bb": 5.059150023723786,
      "best_fixed_action": "raise 5",
      "one_step_deviation_gain_bb": 0.032874976276213275,
      "jam_minus_best_small_bb": -0.8328499999999996,
      "paired_se_bb": 0.08054305405251039,
      "warnings": [],
      "actions": [
        {
          "action": "fold",
          "ci95_bb": [
            0.0,
            0.0
          ],
          "estimated_regret_bb": -5.059150023723786,
          "jam_difference_se_bb": 0.08891482042644323,
          "jam_minus_action_bb": 4.259175,
          "mean_bb": 0.0,
          "probability": 1.4405344472834258e-08,
          "regret_se_bb": 0.09452807000081404,
          "samples": 10000,
          "se_bb": 0.0,
          "stored_cumulative_regret_half_bb": -452228.375,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "raise 4",
          "ci95_bb": [
            4.746906146454405,
            5.143643853545594
          ],
          "estimated_regret_bb": -0.11387502372378658,
          "jam_difference_se_bb": 0.08632095232144377,
          "jam_minus_action_bb": -0.6861,
          "mean_bb": 4.945275,
          "probability": 0.2212858647108078,
          "regret_se_bb": 0.06419527226051988,
          "samples": 10000,
          "se_bb": 0.1012085987477524,
          "stored_cumulative_regret_half_bb": 1428.989990234375,
          "current_regret_matching_probability": 0.5937490394799482
        },
        {
          "action": "raise 5",
          "ci95_bb": [
            4.895309266970468,
            5.288740733029531
          ],
          "estimated_regret_bb": 0.03287497627621342,
          "jam_difference_se_bb": 0.08054305405251039,
          "jam_minus_action_bb": -0.83285,
          "mean_bb": 5.092025,
          "probability": 0.7782326340675354,
          "regret_se_bb": 0.018264170419644454,
          "samples": 10000,
          "se_bb": 0.10036516991302644,
          "stored_cumulative_regret_half_bb": 977.73388671875,
          "current_regret_matching_probability": 0.40625096052005183
        },
        {
          "action": "allin",
          "ci95_bb": [
            4.084901951964171,
            4.433448048035829
          ],
          "estimated_regret_bb": -0.7999750237237866,
          "jam_difference_se_bb": 0.0,
          "jam_minus_action_bb": 0.0,
          "mean_bb": 4.259175,
          "probability": 0.00048144080210477114,
          "regret_se_bb": 0.0743183592720134,
          "samples": 10000,
          "se_bb": 0.08891482042644323,
          "stored_cumulative_regret_half_bb": -65344.90234375,
          "current_regret_matching_probability": 0.0
        }
      ]
    },
    {
      "spot": "BTN RFI",
      "hand": "A5s",
      "policy_ev_bb": 0.3491691454857588,
      "best_fixed_action": "raise 4",
      "one_step_deviation_gain_bb": 0.027105854514241245,
      "jam_minus_best_small_bb": -0.14422500000000002,
      "paired_se_bb": 0.09355242244598506,
      "warnings": [],
      "actions": [
        {
          "action": "fold",
          "ci95_bb": [
            0.0,
            0.0
          ],
          "estimated_regret_bb": -0.3491691454857588,
          "jam_difference_se_bb": 0.09954494562442605,
          "jam_minus_action_bb": 0.23205,
          "mean_bb": 0.0,
          "probability": 0.00012453911767806858,
          "regret_se_bb": 0.0789511977675961,
          "samples": 10000,
          "se_bb": 0.0,
          "stored_cumulative_regret_half_bb": -6748.97021484375,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "raise 4",
          "ci95_bb": [
            0.20641862651268772,
            0.5461313734873123
          ],
          "estimated_regret_bb": 0.027105854514241218,
          "jam_difference_se_bb": 0.09355242244598506,
          "jam_minus_action_bb": -0.144225,
          "mean_bb": 0.376275,
          "probability": 0.7872081995010376,
          "regret_se_bb": 0.015990524179460536,
          "samples": 10000,
          "se_bb": 0.0866614150445471,
          "stored_cumulative_regret_half_bb": 1321.7359619140625,
          "current_regret_matching_probability": 0.7092148880315192
        },
        {
          "action": "raise 5",
          "ci95_bb": [
            0.10341473174775304,
            0.42278526825224694
          ],
          "estimated_regret_bb": -0.08606914548575878,
          "jam_difference_se_bb": 0.09331245528428195,
          "jam_minus_action_bb": -0.03105,
          "mean_bb": 0.2631,
          "probability": 0.11635877192020416,
          "regret_se_bb": 0.07045304171669885,
          "samples": 10000,
          "se_bb": 0.08147207563890152,
          "stored_cumulative_regret_half_bb": 541.9248046875,
          "current_regret_matching_probability": 0.2907851119684807
        },
        {
          "action": "allin",
          "ci95_bb": [
            0.03694190657612495,
            0.42715809342387506
          ],
          "estimated_regret_bb": -0.11711914548575879,
          "jam_difference_se_bb": 0.0,
          "jam_minus_action_bb": 0.0,
          "mean_bb": 0.23205,
          "probability": 0.09630849957466125,
          "regret_se_bb": 0.08061383498594765,
          "samples": 10000,
          "se_bb": 0.09954494562442605,
          "stored_cumulative_regret_half_bb": -8260.91015625,
          "current_regret_matching_probability": 0.0
        }
      ]
    },
    {
      "spot": "BTN RFI",
      "hand": "22",
      "policy_ev_bb": -0.06789442846477031,
      "best_fixed_action": "fold",
      "one_step_deviation_gain_bb": 0.06789442846477031,
      "jam_minus_best_small_bb": -0.1033,
      "paired_se_bb": 0.10625327353457718,
      "warnings": [],
      "actions": [
        {
          "action": "fold",
          "ci95_bb": [
            0.0,
            0.0
          ],
          "estimated_regret_bb": 0.06789442846477031,
          "jam_difference_se_bb": 0.11116512282390212,
          "jam_minus_action_bb": -0.1144,
          "mean_bb": 0.0,
          "probability": 0.024945886805653572,
          "regret_se_bb": 0.07017175212831266,
          "samples": 10000,
          "se_bb": 0.0,
          "stored_cumulative_regret_half_bb": -1034.9180908203125,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "raise 4",
          "ci95_bb": [
            -0.2894177752930903,
            0.06381777529309034
          ],
          "estimated_regret_bb": -0.044905571535229685,
          "jam_difference_se_bb": 0.10830834023128766,
          "jam_minus_action_bb": -0.0016,
          "mean_bb": -0.1128,
          "probability": 0.46009695529937744,
          "regret_se_bb": 0.04607630385751995,
          "samples": 10000,
          "se_bb": 0.09011110984341343,
          "stored_cumulative_regret_half_bb": 886.6991577148438,
          "current_regret_matching_probability": 0.22369567243553412
        },
        {
          "action": "raise 5",
          "ci95_bb": [
            -0.172556494597186,
            0.150356494597186
          ],
          "estimated_regret_bb": 0.05679442846477032,
          "jam_difference_se_bb": 0.10625327353457718,
          "jam_minus_action_bb": -0.1033,
          "mean_bb": -0.0111,
          "probability": 0.4154462516307831,
          "regret_se_bb": 0.04933834586208757,
          "samples": 10000,
          "se_bb": 0.0823757625495847,
          "stored_cumulative_regret_half_bb": 3077.16455078125,
          "current_regret_matching_probability": 0.7763043275644659
        },
        {
          "action": "allin",
          "ci95_bb": [
            -0.3322836407348482,
            0.10348364073484814
          ],
          "estimated_regret_bb": -0.04650557153522968,
          "jam_difference_se_bb": 0.0,
          "jam_minus_action_bb": 0.0,
          "mean_bb": -0.1144,
          "probability": 0.09951082617044449,
          "regret_se_bb": 0.0868047075535079,
          "samples": 10000,
          "se_bb": 0.11116512282390212,
          "stored_cumulative_regret_half_bb": -2516.682373046875,
          "current_regret_matching_probability": 0.0
        }
      ]
    },
    {
      "spot": "BTN RFI",
      "hand": "Q5o",
      "policy_ev_bb": -9.35481946355594e-05,
      "best_fixed_action": "fold",
      "one_step_deviation_gain_bb": 9.35481946355594e-05,
      "jam_minus_best_small_bb": -0.10634999999999994,
      "paired_se_bb": 0.099126612603693,
      "warnings": [],
      "actions": [
        {
          "action": "fold",
          "ci95_bb": [
            0.0,
            0.0
          ],
          "estimated_regret_bb": 9.354819463555941e-05,
          "jam_difference_se_bb": 0.10624418333442655,
          "jam_minus_action_bb": -1.19345,
          "mean_bb": 0.0,
          "probability": 0.9999240636825562,
          "regret_se_bb": 6.740125456187772e-06,
          "samples": 10000,
          "se_bb": 0.0,
          "stored_cumulative_regret_half_bb": 645.4161987304688,
          "current_regret_matching_probability": 1.0
        },
        {
          "action": "raise 4",
          "ci95_bb": [
            -1.2817712992102535,
            -0.8924287007897466
          ],
          "estimated_regret_bb": -1.0870064518052438,
          "jam_difference_se_bb": 0.099126612603693,
          "jam_minus_action_bb": -0.10635,
          "mean_bb": -1.0871,
          "probability": 1.7838259736890905e-05,
          "regret_se_bb": 0.0993171395207862,
          "samples": 10000,
          "se_bb": 0.09932209143380277,
          "stored_cumulative_regret_half_bb": -22490.5625,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "raise 5",
          "ci95_bb": [
            -1.479592174386824,
            -1.0919578256131757
          ],
          "estimated_regret_bb": -1.2856814518052422,
          "jam_difference_se_bb": 0.09325098020379409,
          "jam_minus_action_bb": 0.092325,
          "mean_bb": -1.285775,
          "probability": 5.287037492962554e-05,
          "regret_se_bb": 0.09887978385269423,
          "samples": 10000,
          "se_bb": 0.09888631346266542,
          "stored_cumulative_regret_half_bb": -19426.01171875,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "allin",
          "ci95_bb": [
            -1.401688599335476,
            -0.9852114006645238
          ],
          "estimated_regret_bb": -1.1933564518052449,
          "jam_difference_se_bb": 0.0,
          "jam_minus_action_bb": 0.0,
          "mean_bb": -1.19345,
          "probability": 5.175596925255377e-06,
          "regret_se_bb": 0.10623960471854943,
          "samples": 10000,
          "se_bb": 0.10624418333442655,
          "stored_cumulative_regret_half_bb": -158357.671875,
          "current_regret_matching_probability": 0.0
        }
      ]
    },
    {
      "spot": "UTG 2BB -> BTN",
      "hand": "53s",
      "policy_ev_bb": -0.0002348287618688303,
      "best_fixed_action": "fold",
      "one_step_deviation_gain_bb": 0.0002348287618688303,
      "jam_minus_best_small_bb": 0.928750000190735,
      "paired_se_bb": 0.14983768432318942,
      "warnings": [],
      "actions": [
        {
          "action": "fold",
          "ci95_bb": [
            0.0,
            0.0
          ],
          "estimated_regret_bb": 0.00023482876186883028,
          "jam_difference_se_bb": 0.16864747065244637,
          "jam_minus_action_bb": -1.9344166664123534,
          "mean_bb": 0.0,
          "probability": 0.9999064803123474,
          "regret_se_bb": 1.2138776371036276e-05,
          "samples": 10000,
          "se_bb": 0.0,
          "stored_cumulative_regret_half_bb": 154.77310180664062,
          "current_regret_matching_probability": 1.0
        },
        {
          "action": "call",
          "ci95_bb": [
            -2.7371955588046153,
            -2.178171107989208
          ],
          "estimated_regret_bb": -2.4574485046349133,
          "jam_difference_se_bb": 0.17618480780827844,
          "jam_minus_action_bb": 0.5232666669845581,
          "mean_bb": -2.4576833333969117,
          "probability": 7.73737410781905e-05,
          "regret_se_bb": 0.14259631309590165,
          "samples": 10000,
          "se_bb": 0.14260827826923653,
          "stored_cumulative_regret_half_bb": -15498.4765625,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "raise 14",
          "ci95_bb": [
            -3.1451073739301396,
            -2.581225959276037
          ],
          "estimated_regret_bb": -2.862931837841097,
          "jam_difference_se_bb": 0.14983768432318942,
          "jam_minus_action_bb": 0.9287500001907348,
          "mean_bb": -2.8631666666030884,
          "probability": 1.4589524653274566e-05,
          "regret_se_bb": 0.1438406568816257,
          "samples": 10000,
          "se_bb": 0.14384729965665874,
          "stored_cumulative_regret_half_bb": -17815.896484375,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "allin",
          "ci95_bb": [
            -2.264965708891148,
            -1.6038676239335585
          ],
          "estimated_regret_bb": -1.9341818376503317,
          "jam_difference_se_bb": 0.0,
          "jam_minus_action_bb": 0.0,
          "mean_bb": -1.9344166664123534,
          "probability": 1.4972820281400345e-06,
          "regret_se_bb": 0.16864199533370297,
          "samples": 10000,
          "se_bb": 0.16864747065244637,
          "stored_cumulative_regret_half_bb": -19507.111328125,
          "current_regret_matching_probability": 0.0
        }
      ]
    },
    {
      "spot": "UTG 2BB -> BTN",
      "hand": "AQo",
      "policy_ev_bb": 0.9024797382170127,
      "best_fixed_action": "call",
      "one_step_deviation_gain_bb": 0.07486192819534088,
      "jam_minus_best_small_bb": 0.12048333320617677,
      "paired_se_bb": 0.13541296852158313,
      "warnings": [],
      "actions": [
        {
          "action": "fold",
          "ci95_bb": [
            0.0,
            0.0
          ],
          "estimated_regret_bb": -0.9024797382170126,
          "jam_difference_se_bb": 0.155733480602301,
          "jam_minus_action_bb": 0.48207499980926516,
          "mean_bb": 0.0,
          "probability": 2.0588677429600466e-08,
          "regret_se_bb": 0.16089436193939746,
          "samples": 10000,
          "se_bb": 0.0,
          "stored_cumulative_regret_half_bb": -26722.517578125,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "call",
          "ci95_bb": [
            0.6403275973262609,
            1.314355735498446
          ],
          "estimated_regret_bb": 0.07486192819534093,
          "jam_difference_se_bb": 0.16468873333155196,
          "jam_minus_action_bb": -0.4952666666030884,
          "mean_bb": 0.9773416664123535,
          "probability": 0.8720892667770386,
          "regret_se_bb": 0.02059706957682918,
          "samples": 10000,
          "se_bb": 0.1719459536153534,
          "stored_cumulative_regret_half_bb": 2576.894287109375,
          "current_regret_matching_probability": 1.0
        },
        {
          "action": "raise 14",
          "ci95_bb": [
            0.03492276731818128,
            0.6882605658879954
          ],
          "estimated_regret_bb": -0.5408880716139242,
          "jam_difference_se_bb": 0.13541296852158313,
          "jam_minus_action_bb": 0.12048333320617675,
          "mean_bb": 0.3615916666030884,
          "probability": 0.09554847329854965,
          "regret_se_bb": 0.15350655197145732,
          "samples": 10000,
          "se_bb": 0.16666780575760567,
          "stored_cumulative_regret_half_bb": -3496.947509765625,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "allin",
          "ci95_bb": [
            0.1768373778287552,
            0.7873126217897751
          ],
          "estimated_regret_bb": -0.4204047384077474,
          "jam_difference_se_bb": 0.0,
          "jam_minus_action_bb": 0.0,
          "mean_bb": 0.48207499980926516,
          "probability": 0.03236224502325058,
          "regret_se_bb": 0.14855792018871508,
          "samples": 10000,
          "se_bb": 0.155733480602301,
          "stored_cumulative_regret_half_bb": -6292.89501953125,
          "current_regret_matching_probability": 0.0
        }
      ]
    }
  ],
  "seed101-84m": [
    {
      "spot": "BTN RFI",
      "hand": "AQo",
      "policy_ev_bb": 1.6292277684979142,
      "best_fixed_action": "raise 4",
      "one_step_deviation_gain_bb": 0.08299723150208593,
      "jam_minus_best_small_bb": -0.14332500000000015,
      "paired_se_bb": 0.09056465433655124,
      "warnings": [],
      "actions": [
        {
          "action": "fold",
          "ci95_bb": [
            0.0,
            0.0
          ],
          "estimated_regret_bb": -1.6292277684979142,
          "jam_difference_se_bb": 0.09446566918868211,
          "jam_minus_action_bb": 1.5689,
          "mean_bb": 0.0,
          "probability": 3.955901561880637e-08,
          "regret_se_bb": 0.09621041549846035,
          "samples": 10000,
          "se_bb": 0.0,
          "stored_cumulative_regret_half_bb": -264485.90625,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "raise 4",
          "ci95_bb": [
            1.5067710748800778,
            1.9176789251199224
          ],
          "estimated_regret_bb": 0.08299723150208592,
          "jam_difference_se_bb": 0.09056465433655124,
          "jam_minus_action_bb": -0.143325,
          "mean_bb": 1.712225,
          "probability": 0.4849074184894562,
          "regret_se_bb": 0.0451813863612011,
          "samples": 10000,
          "se_bb": 0.1048234311836338,
          "stored_cumulative_regret_half_bb": 2455.563232421875,
          "current_regret_matching_probability": 0.47946341786639934
        },
        {
          "action": "raise 5",
          "ci95_bb": [
            1.3406519905251335,
            1.7609980094748663
          ],
          "estimated_regret_bb": -0.07840276849791408,
          "jam_difference_se_bb": 0.08369459171837682,
          "jam_minus_action_bb": 0.018075,
          "mean_bb": 1.550825,
          "probability": 0.5074132084846497,
          "regret_se_bb": 0.043090937079081064,
          "samples": 10000,
          "se_bb": 0.1072311272830951,
          "stored_cumulative_regret_half_bb": 2665.918701171875,
          "current_regret_matching_probability": 0.5205365821336007
        },
        {
          "action": "allin",
          "ci95_bb": [
            1.383747288390183,
            1.754052711609817
          ],
          "estimated_regret_bb": -0.060327768497914075,
          "jam_difference_se_bb": 0.0,
          "jam_minus_action_bb": 0.0,
          "mean_bb": 1.5689,
          "probability": 0.00767931342124939,
          "regret_se_bb": 0.07454387010550832,
          "samples": 10000,
          "se_bb": 0.09446566918868211,
          "stored_cumulative_regret_half_bb": -6516.6708984375,
          "current_regret_matching_probability": 0.0
        }
      ]
    },
    {
      "spot": "BTN RFI",
      "hand": "AA",
      "policy_ev_bb": 4.902204039830808,
      "best_fixed_action": "raise 5",
      "one_step_deviation_gain_bb": 0.1255709601691919,
      "jam_minus_best_small_bb": -0.8247999999999998,
      "paired_se_bb": 0.07896602313198334,
      "warnings": [],
      "actions": [
        {
          "action": "fold",
          "ci95_bb": [
            0.0,
            0.0
          ],
          "estimated_regret_bb": -4.902204039830807,
          "jam_difference_se_bb": 0.08476919736330916,
          "jam_minus_action_bb": 4.202975,
          "mean_bb": 0.0,
          "probability": 2.637815654793485e-08,
          "regret_se_bb": 0.09163711792744728,
          "samples": 10000,
          "se_bb": 0.0,
          "stored_cumulative_regret_half_bb": -397517.6875,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "raise 4",
          "ci95_bb": [
            4.636865490431845,
            5.022284509568156
          ],
          "estimated_regret_bb": -0.0726290398308076,
          "jam_difference_se_bb": 0.0831114266808391,
          "jam_minus_action_bb": -0.6266,
          "mean_bb": 4.829575,
          "probability": 0.6212183833122253,
          "regret_se_bb": 0.03040157967443557,
          "samples": 10000,
          "se_bb": 0.09832117835109959,
          "stored_cumulative_regret_half_bb": 2044.95947265625,
          "current_regret_matching_probability": 0.6355234297725189
        },
        {
          "action": "raise 5",
          "ci95_bb": [
            4.827986165921741,
            5.227563834078259
          ],
          "estimated_regret_bb": 0.1255709601691924,
          "jam_difference_se_bb": 0.07896602313198334,
          "jam_minus_action_bb": -0.8248,
          "mean_bb": 5.027775,
          "probability": 0.3758167028427124,
          "regret_se_bb": 0.05014175432746192,
          "samples": 10000,
          "se_bb": 0.10193307861135667,
          "stored_cumulative_regret_half_bb": 1172.7967529296875,
          "current_regret_matching_probability": 0.3644765702274811
        },
        {
          "action": "allin",
          "ci95_bb": [
            4.036827373167914,
            4.369122626832087
          ],
          "estimated_regret_bb": -0.6992290398308076,
          "jam_difference_se_bb": 0.0,
          "jam_minus_action_bb": 0.0,
          "mean_bb": 4.202975,
          "probability": 0.0029649101197719574,
          "regret_se_bb": 0.07141682606694398,
          "samples": 10000,
          "se_bb": 0.08476919736330916,
          "stored_cumulative_regret_half_bb": -57983.48828125,
          "current_regret_matching_probability": 0.0
        }
      ]
    },
    {
      "spot": "BTN RFI",
      "hand": "A5s",
      "policy_ev_bb": 0.3123217884179205,
      "best_fixed_action": "raise 4",
      "one_step_deviation_gain_bb": 0.0176282115820795,
      "jam_minus_best_small_bb": -0.28340000000000004,
      "paired_se_bb": 0.0913056384675207,
      "warnings": [],
      "actions": [
        {
          "action": "fold",
          "ci95_bb": [
            0.0,
            0.0
          ],
          "estimated_regret_bb": -0.31232178841792047,
          "jam_difference_se_bb": 0.0971541092895467,
          "jam_minus_action_bb": 0.04655,
          "mean_bb": 0.0,
          "probability": 1.2490451339886022e-08,
          "regret_se_bb": 0.08091436961787873,
          "samples": 10000,
          "se_bb": 0.0,
          "stored_cumulative_regret_half_bb": -12719.3623046875,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "raise 4",
          "ci95_bb": [
            0.1642822218969852,
            0.4956177781030149
          ],
          "estimated_regret_bb": 0.017628211582079528,
          "jam_difference_se_bb": 0.0913056384675207,
          "jam_minus_action_bb": -0.2834,
          "mean_bb": 0.32995,
          "probability": 0.9100556373596191,
          "regret_se_bb": 0.006790065902837087,
          "samples": 10000,
          "se_bb": 0.08452437658317083,
          "stored_cumulative_regret_half_bb": 1427.45654296875,
          "current_regret_matching_probability": 1.0
        },
        {
          "action": "raise 5",
          "ci95_bb": [
            0.08929804897862476,
            0.39210195102137524
          ],
          "estimated_regret_bb": -0.07162178841792047,
          "jam_difference_se_bb": 0.09395542608045049,
          "jam_minus_action_bb": -0.19415,
          "mean_bb": 0.2407,
          "probability": 0.040494561195373535,
          "regret_se_bb": 0.08028300489153063,
          "samples": 10000,
          "se_bb": 0.07724589337825268,
          "stored_cumulative_regret_half_bb": -503.5700378417969,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "allin",
          "ci95_bb": [
            -0.1438720542075115,
            0.23697205420751152
          ],
          "estimated_regret_bb": -0.2657717884179205,
          "jam_difference_se_bb": 0.0,
          "jam_minus_action_bb": 0.0,
          "mean_bb": 0.04655,
          "probability": 0.04944983869791031,
          "regret_se_bb": 0.08533070118559825,
          "samples": 10000,
          "se_bb": 0.0971541092895467,
          "stored_cumulative_regret_half_bb": -9935.724609375,
          "current_regret_matching_probability": 0.0
        }
      ]
    },
    {
      "spot": "BTN RFI",
      "hand": "22",
      "policy_ev_bb": 0.07314034769897598,
      "best_fixed_action": "raise 5",
      "one_step_deviation_gain_bb": 0.070634652301024,
      "jam_minus_best_small_bb": -0.06192499999999998,
      "paired_se_bb": 0.10748989516319066,
      "warnings": [],
      "actions": [
        {
          "action": "fold",
          "ci95_bb": [
            0.0,
            0.0
          ],
          "estimated_regret_bb": -0.07314034769897598,
          "jam_difference_se_bb": 0.11001921073350346,
          "jam_minus_action_bb": 0.08185,
          "mean_bb": 0.0,
          "probability": 0.35931506752967834,
          "regret_se_bb": 0.04301424319115576,
          "samples": 10000,
          "se_bb": 0.0,
          "stored_cumulative_regret_half_bb": -626.4560546875,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "raise 4",
          "ci95_bb": [
            -0.10025182955274903,
            0.20295182955274904
          ],
          "estimated_regret_bb": -0.021790347698975983,
          "jam_difference_se_bb": 0.10915211126377417,
          "jam_minus_action_bb": 0.0305,
          "mean_bb": 0.05135,
          "probability": 0.20528016984462738,
          "regret_se_bb": 0.057886802725145216,
          "samples": 10000,
          "se_bb": 0.07734787222079033,
          "stored_cumulative_regret_half_bb": 998.3073120117188,
          "current_regret_matching_probability": 0.4200336930551429
        },
        {
          "action": "raise 5",
          "ci95_bb": [
            -0.011009674748224313,
            0.2985596747482243
          ],
          "estimated_regret_bb": 0.07063465230102402,
          "jam_difference_se_bb": 0.10748989516319066,
          "jam_minus_action_bb": -0.061925,
          "mean_bb": 0.143775,
          "probability": 0.4353867769241333,
          "regret_se_bb": 0.041242548378323245,
          "samples": 10000,
          "se_bb": 0.07897177283072669,
          "stored_cumulative_regret_half_bb": 1378.4241943359375,
          "current_regret_matching_probability": 0.5799663069448572
        },
        {
          "action": "allin",
          "ci95_bb": [
            -0.13378765303766676,
            0.2974876530376668
          ],
          "estimated_regret_bb": 0.008709652301024016,
          "jam_difference_se_bb": 0.0,
          "jam_minus_action_bb": 0.0,
          "mean_bb": 0.08185,
          "probability": 1.8046734112431295e-05,
          "regret_se_bb": 0.09865109940991967,
          "samples": 10000,
          "se_bb": 0.11001921073350346,
          "stored_cumulative_regret_half_bb": -6691.669921875,
          "current_regret_matching_probability": 0.0
        }
      ]
    },
    {
      "spot": "BTN RFI",
      "hand": "Q5o",
      "policy_ev_bb": -2.117279670613925e-05,
      "best_fixed_action": "fold",
      "one_step_deviation_gain_bb": 2.117279670613925e-05,
      "jam_minus_best_small_bb": -0.12624999999999997,
      "paired_se_bb": 0.09514446957526788,
      "warnings": [],
      "actions": [
        {
          "action": "fold",
          "ci95_bb": [
            0.0,
            0.0
          ],
          "estimated_regret_bb": 2.1172796706139253e-05,
          "jam_difference_se_bb": 0.10539819792790646,
          "jam_minus_action_bb": -1.198875,
          "mean_bb": 0.0,
          "probability": 0.9999812841415405,
          "regret_se_bb": 1.5776527060342635e-06,
          "samples": 10000,
          "se_bb": 0.0,
          "stored_cumulative_regret_half_bb": 377.7962951660156,
          "current_regret_matching_probability": 1.0
        },
        {
          "action": "raise 4",
          "ci95_bb": [
            -1.4662799720475905,
            -1.0701200279524095
          ],
          "estimated_regret_bb": -1.2681788272034238,
          "jam_difference_se_bb": 0.09806635116267218,
          "jam_minus_action_bb": 0.069325,
          "mean_bb": -1.2682,
          "probability": 2.7144835712533677e-06,
          "regret_se_bb": 0.10106005435203783,
          "samples": 10000,
          "se_bb": 0.10106121022836251,
          "stored_cumulative_regret_half_bb": -19440.06640625,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "raise 5",
          "ci95_bb": [
            -1.2569349155379168,
            -0.8883150844620831
          ],
          "estimated_regret_bb": -1.0726038272033873,
          "jam_difference_se_bb": 0.09514446957526788,
          "jam_minus_action_bb": -0.12625,
          "mean_bb": -1.072625,
          "probability": 1.0881329217227176e-05,
          "regret_se_bb": 0.09403419721284491,
          "samples": 10000,
          "se_bb": 0.09403567119281474,
          "stored_cumulative_regret_half_bb": -19538.509765625,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "allin",
          "ci95_bb": [
            -1.4054554679386966,
            -0.9922945320613032
          ],
          "estimated_regret_bb": -1.1988538272033924,
          "jam_difference_se_bb": 0.0,
          "jam_minus_action_bb": 0.0,
          "mean_bb": -1.198875,
          "probability": 5.053656877862522e-06,
          "regret_se_bb": 0.10539695194742209,
          "samples": 10000,
          "se_bb": 0.10539819792790646,
          "stored_cumulative_regret_half_bb": -141611.15625,
          "current_regret_matching_probability": 0.0
        }
      ]
    },
    {
      "spot": "UTG 2BB -> BTN",
      "hand": "53s",
      "policy_ev_bb": -0.001470879307964753,
      "best_fixed_action": "fold",
      "one_step_deviation_gain_bb": 0.001470879307964753,
      "jam_minus_best_small_bb": 1.6208333337783816,
      "paired_se_bb": 0.16061474931044303,
      "warnings": [],
      "actions": [
        {
          "action": "fold",
          "ci95_bb": [
            0.0,
            0.0
          ],
          "estimated_regret_bb": 0.0014708793079647527,
          "jam_difference_se_bb": 0.17107585606416809,
          "jam_minus_action_bb": -1.588374999809265,
          "mean_bb": 0.0,
          "probability": 0.9990833401679993,
          "regret_se_bb": 0.00015583439387713437,
          "samples": 10000,
          "se_bb": 0.0,
          "stored_cumulative_regret_half_bb": 419.7413330078125,
          "current_regret_matching_probability": 1.0
        },
        {
          "action": "call",
          "ci95_bb": [
            -3.1777971790951884,
            -2.567119487698635
          ],
          "estimated_regret_bb": -2.870987454088972,
          "jam_difference_se_bb": 0.16922599762122903,
          "jam_minus_action_bb": 1.2840833335876465,
          "mean_bb": -2.872458333396912,
          "probability": 5.584742211794946e-06,
          "regret_se_bb": 0.15571158397862978,
          "samples": 10000,
          "se_bb": 0.15578512535626363,
          "stored_cumulative_regret_half_bb": -14343.38671875,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "raise 14",
          "ci95_bb": [
            -3.4987668514494223,
            -2.919649815725871
          ],
          "estimated_regret_bb": -3.207737454279711,
          "jam_difference_se_bb": 0.16061474931044303,
          "jam_minus_action_bb": 1.6208333337783813,
          "mean_bb": -3.2092083335876467,
          "probability": 4.67018026029109e-06,
          "regret_se_bb": 0.1476553362411123,
          "samples": 10000,
          "se_bb": 0.14773393768457938,
          "stored_cumulative_regret_half_bb": -21385.03125,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "allin",
          "ci95_bb": [
            -1.9236836776950346,
            -1.2530663219234957
          ],
          "estimated_regret_bb": -1.586904120501379,
          "jam_difference_se_bb": 0.0,
          "jam_minus_action_bb": 0.0,
          "mean_bb": -1.588374999809265,
          "probability": 0.0009064923506230116,
          "regret_se_bb": 0.1709200254438645,
          "samples": 10000,
          "se_bb": 0.17107585606416809,
          "stored_cumulative_regret_half_bb": -9973.51953125,
          "current_regret_matching_probability": 0.0
        }
      ]
    },
    {
      "spot": "UTG 2BB -> BTN",
      "hand": "AQo",
      "policy_ev_bb": 0.8490494947818965,
      "best_fixed_action": "call",
      "one_step_deviation_gain_bb": 0.14997550521810354,
      "jam_minus_best_small_bb": 0.44590000019073484,
      "paired_se_bb": 0.15284796262975292,
      "warnings": [],
      "actions": [
        {
          "action": "fold",
          "ci95_bb": [
            0.0,
            0.0
          ],
          "estimated_regret_bb": -0.8490494947818966,
          "jam_difference_se_bb": 0.16166965902385147,
          "jam_minus_action_bb": 0.9623166666030883,
          "mean_bb": 0.0,
          "probability": 2.0734023564727977e-05,
          "regret_se_bb": 0.1561047188779729,
          "samples": 10000,
          "se_bb": 0.0,
          "stored_cumulative_regret_half_bb": -27236.306640625,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "call",
          "ci95_bb": [
            0.6513120202105217,
            1.3467379797894785
          ],
          "estimated_regret_bb": 0.14997550521810357,
          "jam_difference_se_bb": 0.17087786726786044,
          "jam_minus_action_bb": -0.036708333396911624,
          "mean_bb": 0.999025,
          "probability": 0.6819056272506714,
          "regret_se_bb": 0.05569539367226816,
          "samples": 10000,
          "se_bb": 0.17740458152524405,
          "stored_cumulative_regret_half_bb": 1858.89794921875,
          "current_regret_matching_probability": 1.0
        },
        {
          "action": "raise 14",
          "ci95_bb": [
            0.17280385842662838,
            0.8600294743980786
          ],
          "estimated_regret_bb": -0.3326328283695429,
          "jam_difference_se_bb": 0.15284796262975292,
          "jam_minus_action_bb": 0.4459000001907349,
          "mean_bb": 0.5164166664123535,
          "probability": 0.3101117014884949,
          "regret_se_bb": 0.12118400162536941,
          "samples": 10000,
          "se_bb": 0.17531265713557406,
          "stored_cumulative_regret_half_bb": -5962.03564453125,
          "current_regret_matching_probability": 0.0
        },
        {
          "action": "allin",
          "ci95_bb": [
            0.6454441349163395,
            1.2791891982898371
          ],
          "estimated_regret_bb": 0.11326717182119196,
          "jam_difference_se_bb": 0.0,
          "jam_minus_action_bb": 0.0,
          "mean_bb": 0.9623166666030883,
          "probability": 0.007961905561387539,
          "regret_se_bb": 0.1425654443266816,
          "samples": 10000,
          "se_bb": 0.16166965902385147,
          "stored_cumulative_regret_half_bb": -8727.04296875,
          "current_regret_matching_probability": 0.0
        }
      ]
    }
  ]
}

{
  "seed42-80m": [
    {
      "spot": "UTG 2BB -> BTN",
      "hand": "AQo",
      "action": "call",
      "reason": "profitable frozen-policy one-step deviation; not a NashConv estimate",
      "advantage_bb": 0.2583806968338537,
      "se_bb": 0.042969224596331033
    },
    {
      "spot": "UTG 2BB -> BTN",
      "hand": "AQo",
      "action": "raise 14",
      "reason": "material average probability with significantly negative frozen-policy advantage",
      "advantage_bb": -0.8441693027846766,
      "se_bb": 0.13411254081389984
    }
  ],
  "seed73-95m": [
    {
      "spot": "UTG 2BB -> BTN",
      "hand": "AQo",
      "action": "raise 14",
      "reason": "material average probability with significantly negative frozen-policy advantage",
      "advantage_bb": -0.5408880716139242,
      "se_bb": 0.15350655197145732
    }
  ],
  "seed101-84m": [
    {
      "spot": "UTG 2BB -> BTN",
      "hand": "AQo",
      "action": "raise 14",
      "reason": "material average probability with significantly negative frozen-policy advantage",
      "advantage_bb": -0.3326328283695429,
      "se_bb": 0.12118400162536941
    }
  ]
}

{
  "101": "SB RFI: Q5s anomalously worse than Q5o"
}

## 限界

全6人NLHEのNashConvは未計算。公開情報・private hand abstraction、有限サイズ、各street最大1段raiseを使用。CPUの実ゲームpostflopは簡易方策。標準誤差はMC誤差のみ。JSONは学習出力をそのままコピー。科学的な正式リリース判定は未通過のまま保存する。