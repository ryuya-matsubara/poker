# 6-max・20BB プリフロップモデルの修正

## 根本原因の切り分け

workflow、preflop_charts.json、preflop_policy.json、exporter、画面のhandBucket / solverHistory / heroStrategyAdvice、pinned DCFR-SOLVER 4ade6a9e15a841c41867afde1258b9d110cd6fb1 のsrc/preflop.rsを確認した。Q5oのbucketは139、3回のFold後のBTN RFI履歴は000000で、旧JSONに約96% Raiseが保存されていた。表示処理の問題ではない。

旧補正はheads-upの終端で OOPからIPへ POT×tax×position gap/5 を勝敗と無関係に直接移す。BTN–BBならtax0.20の16%、BTN–SBなら20%。5.5BBのBTN–BBポットなら0.88BBを移す。オールインでもこの位置移転が適用され、判断する余地のない終端にも位置価値を加えていた。

同じseed42・30m・20BB・同じ行動候補でtaxだけを変更した比較：
| Tax | UTG | HJ/MP | CO | BTN | SB Raise | SB Limp | BTN Q5o |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.00 | 11.5% | 13.0% | 16.7% | 22.7% | 22.1% | 66.4% | 1.2% |
| 0.05 | 11.7% | 14.7% | 20.9% | 33.3% | 19.3% | 64.1% | 2.4% |
| 0.10 | 11.4% | 15.4% | 24.3% | 45.4% | 17.1% | 61.7% | 5.6% |
| 0.20 | 9.6% | 15.0% | 27.5% | 74.2% | 13.2% | 57.3% | 96.5% |

[169クラス×5位置×4条件の全頻度](tax_sensitivity_169.csv)を保存した。BTNで95/169クラスが50ポイント超変化したため、Q5oだけの問題ではない。0.20の再実行は旧JSONの全確率を再現した。固定位置移転が過大評価の直接の主因と判断できる。

raw showdownは全員に無料で最後までボードを見せるため、弱いコール側のequity realizationを過大評価する一方、IPのベットによるfold equityや将来のvalue betも省略する。単にtaxを0にすれば正しいEVになるわけではない。基本的なチップ精算とside potを保持し、実際のBet/Call/Fold後の損益へ置き換えた。チップ精算自体が正しくzero-sumでも、固定税を加えたゲームが実際のNLHEを表すことにはならない。

旧rawモデルのopen-size 2/2.5/3BB比較ではBTN総open22.8/22.7/22.2%だった（[全169頻度](open_size_169.csv)）。この額だけで旧異常を説明できない。ただし新しいcontinuationやopen shoveとの相互作用まで、この旧モデルの実験から否定しない。

## 方式の比較と実装

| 方式 | 精度・計算量・Actionsでの実行 | 判定 |
| --- | --- | --- |
| hand class・position・opponent position・SPR・pot typeごとのequity realization表 | 参照は速いが、妥当なEV表を別に作る必要がある。倍率だけでは相手のFold/Callや将来のBetを扱えない | 単独採用しない |
| representative flopの小規模subgameを解いてEV表を作る | 各subgameの精度を測りやすいが、学習中にレンジが変わるため作り直しが必要。例えば15位置ペア×3pot type×3SPR×64flopで8,640のHU solveがあり、multiwayも別途必要。この個数は構成例で、時間の計測値ではない | 今回は別EV表の作成を避ける |
| abstractionしたFlop/Turn/RiverをCFRで学習 | ボードをサンプリングし、プリフロップと同時に戦略を学習する。全ボードと全ベット木の列挙を避けられる。実測時間/RSSは下表 | 採用 |

各ストリートの候補はCheck、1/3 POT Bet、3/4 POT Bet、All-in、ベットに対するCall/Fold。postflop raiseは省略する。役、draw、公開盤面、位置、参加者の位置、SPR、preflop pot typeと主導権、直近のbet履歴をまとめた情報集合でregretを学習する。行動頻度を手で指定しない。全部の過去カード/履歴を記憶しないimperfect-recall abstractionなので、完全なNLHEのsolveではない。

判断特徴は自分のhole cardsとその時点の公開カードのみを使う。相手カードは終端の役判定、未来ボードはchance/終端精算に使う。12枚のholeと5枚のboardは同じ52枚から重複なく配る。オールイン後の判断のない終端はshowdownで精算し、位置移転をしない。ベット後はbettorの次の席から応答し、最小ベットは1BB（小さいall-inを除く）。

プリフロップの候補は2BB/2.5BB Open、SB Limp/3BB Open、7BB 3-bet、14BB 4-bet、Openを含むAll-in。2BBと2.5BBもソルバーが選ぶ。SBの同じ3BB Raiseを重複登録しない。ハードコードされたRFIレンジ、Q5oだけの例外、一律position bonus、目標頻度への事後補正は使っていない。

upstreamの当該preflop trainerはexternal-sampling、regretの非負化、iterationに比例する平均戦略の重みを使うCFR系実装である。リポジトリ名だけからDCFRの保証を仮定しない。postflopも同じ更新方式を使う。

## 検証と外部妥当性の限界

独立seed、学習量、premium/weak、suited/offsuit、位置、全169クラス、probability、20BB/blind、JSON/UIの行動順を検査する。以前の「BTN総openは33%以上」という合否閾値は、同じ20BB/no-ante/no-rakeの独立解に基づいていなかったため、注意事項へ修正した。条件が違う資料の総open率へ頻度を強制的に合わせない。確率破損、premiumの逆転、位置の大きな逆転、不安定なseed/iterationは引き続き検出する。

[GTO Wizard: How Stack Sizes Change Your Range](https://blog.gtowizard.com/how-stack-sizes-change-your-range/)は20BBで2BB openや浅いstackの特徴を説明するが、例には1BB anteがある。[Upswing: Open-Raising with a Short Stack](https://upswingpoker.com/open-raising-with-a-short-stack-tournaments/)もtournament条件。同じ6-max/20BB/no-ante/no-rakeと同じbet abstractionの全169クラスの独立解は公開資料で確認できず、完全一致の精度検証は行っていない。外部データはコードへの入力やハンド別頻度の指定に使っていない。

[Brown & Sandholm, Science 2019](https://doi.org/10.1126/science.aay2400)が説明する通り、2人zero-sumのCFRにあるNash収束保証を6人へそのまま適用できない。以下は経験的な安定性検証で、exploitabilityやGTO Wizard同等精度の証明ではない。実ゲームのpostflop CPU自体は既存の簡易推定で、今回の変更はpreflop戦略生成のcontinuationを改善するもの。

## 最終学習と全169クラスの比較

公開データはseed42・6,000万iteration。[全169ハンド×5位置の各行動頻度と比較条件](final_frequency_169.csv)、[検証の数値](quality.json)を保存した。

| 条件 | UTG | HJ/MP | CO | BTN | SB raise/shove | SB limp |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| raw-mixed-open, seed42, 30m | 25.5% | 26.0% | 27.2% | 31.3% | 35.4% | 23.3% |
| cfr-fixed-2.5bb-diagnostic, seed42, 30m | 21.5% | 22.6% | 24.7% | 29.0% | 30.3% | 36.5% |
| joint-final, seed42, 30m | 25.7% | 26.6% | 28.5% | 32.5% | 33.2% | 28.4% |
| joint-final, seed42, 60m | 21.2% | 21.8% | 23.9% | 28.9% | 29.7% | 36.7% |
| joint-final, seed73, 60m | 21.2% | 22.0% | 24.2% | 29.7% | 30.2% | 36.5% |

raw比較は同じ20BB・seed42・30m・2/2.5BB＋open shove・1 board sampleで、終端だけをraw showdownに戻したもの。fixed-2.5bbはベット額の診断用旧版CFRで、最終版のマルチウェイ順/最小ベット修正前。最終版との全差をベット額だけに帰属させない。

| 位置 | seed差の加重RMS | seed差の総open差 | 学習量差の加重RMS | 学習量差の総open差 |
| --- | ---: | ---: | ---: | ---: |
| UTG RFI | 0.036 | 0.0% | 0.107 | 4.5% |
| HJ RFI | 0.026 | 0.2% | 0.105 | 4.8% |
| CO RFI | 0.032 | 0.2% | 0.096 | 4.5% |
| BTN RFI | 0.069 | 0.7% | 0.082 | 3.6% |
| SB RFI | 0.125 | 0.5% | 0.100 | 3.5% |

RMSは1,326コンボで加重した各ハンドopen頻度の差。sanity checkはRMS≤0.16・総open差≤8ポイント、premium/weak、suited/offsuit、位置、確率、20BBとblindを検査する。これは精度やNash収束の証明ではない。境界ハンドに残る揺れもCSVで確認できる。

外部の条件が違う参考範囲から外れた位置：BTN RFI: outside loose external prior; no identical independent benchmark。頻度を参考範囲へ強制補正していない。

### BTN RFI

| ハンド | Fold | 2BB Raise | 2.5BB Raise | Shove |
| --- | ---: | ---: | ---: | ---: |
| 32o | 98.0% | 0.4% | 0.4% | 1.2% |
| 54o | 97.1% | 0.7% | 0.6% | 1.7% |
| 65o | 96.7% | 0.7% | 0.7% | 1.9% |
| 76o | 96.2% | 1.1% | 0.8% | 1.9% |
| T5o | 97.0% | 0.7% | 0.7% | 1.6% |
| J2o | 97.0% | 0.7% | 0.6% | 1.7% |
| J5o | 96.3% | 0.9% | 0.9% | 2.0% |
| Q2o | 96.9% | 0.8% | 0.7% | 1.7% |
| Q5o | 96.2% | 0.9% | 0.9% | 2.0% |
| Q8o | 93.5% | 1.7% | 2.0% | 2.8% |
| K2o | 95.3% | 1.1% | 0.9% | 2.7% |
| A2o | 86.4% | 4.0% | 3.0% | 6.6% |
| 22 | 76.6% | 2.5% | 3.5% | 17.4% |
| A5s | 3.2% | 17.3% | 13.8% | 65.7% |
| Q5s | 85.9% | 4.1% | 4.2% | 5.8% |

### UTG RFI

| ハンド | Fold | 2BB Raise | 2.5BB Raise | Shove |
| --- | ---: | ---: | ---: | ---: |
| 22 | 95.6% | 1.0% | 1.2% | 2.3% |
| 55 | 11.5% | 46.3% | 22.4% | 19.8% |
| 77 | 0.7% | 58.3% | 27.4% | 13.6% |
| 99 | 0.2% | 46.5% | 35.4% | 18.0% |
| JTs | 5.7% | 28.5% | 42.5% | 23.3% |
| QJs | 1.2% | 53.3% | 19.2% | 26.3% |
| KJs | 0.9% | 28.0% | 58.8% | 12.3% |
| A5s | 3.6% | 21.4% | 29.1% | 45.9% |
| A9s | 1.3% | 11.6% | 63.9% | 23.1% |
| AJo | 0.2% | 44.3% | 38.8% | 16.7% |
| AQo | 0.1% | 27.0% | 49.4% | 23.5% |
| AKs | 0.2% | 14.0% | 25.7% | 60.1% |
| AKo | 0.1% | 48.2% | 31.9% | 19.8% |

### 計算時間と検証

- raw / 30m: 時間 6:27.86, 最大RSS 1410 MiB。
- joint / 30m: 時間 6:47.39, 最大RSS 1619 MiB。
- joint / 60m: 時間 22:16.61, 最大RSS 1673 MiB。
- joint seed73 / 60m: 時間 22:54.75, 最大RSS 1675 MiB。

Q5o bucket139、UTG→MP→CO Fold後のBTN履歴、2/2.5BBとAll-inのaction order、export確率合計、通常位置RFIにCall/Limpがないこと、全員20BB・SB0.5BB/BB1BB、損益保存、未来カードを特徴に入れないこと、キッカー、マルチウェイ応答順、最小1BBベットを自動検証した。
