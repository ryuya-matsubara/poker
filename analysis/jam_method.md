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

相手actionを `q(a)=0.95π(a)+0.05/|A|` でsampleする。traverser actionは全列挙。sampled subtree値にはπ/qを掛ける。到達までのopponent/chance sampling補正をregretに適用し、own reachはregretへ掛けない。平均戦略には `linear_iteration_weight × own_reach / sampled_opponent_reach × π(a)` を加える。chanceは一様な重複なし6人hole dealとrunoutをsampleし、既知のchance sampling項が期待値で相殺する。board、hole card、opponent private stateを戦略判断へ渡さない。

累積regretはsignedで保存し、regret matchingでは正の部分だけを正規化する。全actionが非正ならuniform。sampling correctionのclip、固定bonus、hand-specific penaltyはない。branch間のcommon random numbers用にdecision RNGをcloneしても、次deal/runoutのstreamを巻き戻さないよう、deal・board・decision RNGをepisode seedで分離する。1board/4board、異なる戦略でもdeal streamを同一に保つ。各iterationでpolicyを凍結してから1人のtraverserを巡回更新し、同じinfosetの再訪問で更新途中のpolicyを使わない。checkpoint EV診断は学習RNG/runoutを復元して学習軌跡を変えない。

**多人数とimperfect recall**: 6人ゲームは、2人zero-sumのCFRと同じNash収束保証を持たない。さらに履歴とmoneyのabstractionはimperfect recallである。iteration/seed stabilityは抽象モデル内の安定性であり、NLHE全体のGTO誤差の証明ではない。

## Continuationとterminalの一貫性

全preflop terminalを同じjointモデルへ渡す。non-all-inはFlop/Turn/Riverの実際のfold/call/bet/raiseを通り、all-inは合法なfuture decisionが無いため同じrunout/payoffで精算する。jamへ人工的なbonusは与えない。ただしnon-all-inの近似誤差は残るため、raw/nojam/rich/raises/chance/sizesのablationで相対価値を確認する。

Postflop tree：check、33%pot、75%pot、all-in。bet facing：fold/call、3×またはmin-raiseを満たすraise、all-in。各street最大1raise。新規bet/raiseへの支払は累積street contributionとの差で計算する。short-all-inは未対応者のcallを要求するが既にactionした人のraise権を再開しない。side pot、fold payoff、all-in call、showdownは上流のchip conservation処理を使い、合法ランダムstate 10,000件のpreflop＋postflopで `sum(payoff)≈0`, stacks≥0, stack+contribution=20BBを検証する。

Preflop/Postflopとも169 rank/suited identityを保持し、private keyはboard-relative made/draw、hole high/low rank、overcards、flush/backdoor count、straight potential、A/K nut/near-nut blockerを保持する。made classifierはtop/non-top pair、overpair/underpair、kickerの粗い強度を区別する。middle/bottom pair、gutshot/open-ended/double-gutshotの全種類は完全には分離せず、rank bands・board bins・straight potentialとの組合せで近似する。完全な1326 suit-labelled identity、全backdoor種類、正確なrange-relative equity/nut advantageは保持しない。nut blockerはboard suitに対するprivate featureであり、相手rangeに対する完全なnut advantageではない。

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
