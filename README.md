> 現在の公開版はユーザー指示により途中学習結果を採用した実験版です。seed42 80Mを使用し、seed73 95M・seed101 84Mと比較しています。120M・収束確認は未完了です。CPU全体をGTOとみなさないでください。

# POKER ROOM

ブラウザーで遊べる、シングルプレイのノーリミット・テキサスホールデムです。GitHub Pagesで公開する静的Webアプリです。

## ルール

- 6人卓固定（あなた＋CPU1〜CPU5）
- 開始スタック20BB、ブラインド0.5/1BB、アンティなし、レーキなし
- 1BB = ¥1,000。持ち点はハンド間で引き継ぎ、破産時に20BBでリバイ
- 毎ハンド52枚をシャッフルし、重複なく配布
- フォールド、チェック、コール、ベット、レイズ、オールイン、サイドポット、引き分けを処理

## CPUの計算済み戦略

`preflop_policy.json` は6人・20BB向けにMCCFRで計算した、全ての浅い履歴（depth≤4）と頻出の深いプリフロップ履歴ごとの平均戦略です。各履歴で169種類の開始ハンドに対するフォールド、コール、レイズ、オールインの頻度を参照します。未学習の履歴・ハンド、候補外のアクション、開始時に誰かが16〜24BBの範囲外となるハンドには簡易判断を使います。表にない場合でも、未参加のオープン局面は`preflop_charts.json`の戦略を使います。こちらはCPUが16〜24BBで他の参加者に14BB未満がいない場合に適用します。20BB以外への適用は近似です。あなたの手番で戦略表が利用できる場合は、アクション頻度を「参考戦略」として表示します。

計算上のベット候補はオープン2BB・2.5BB（SBは3BB）、3ベット7BB、4ベット14BB、オープンを含むオールインです。これに合わせて画面のプリフロップレイズ候補も調整しています。

計算は公開MITライセンスの [DCFR-SOLVER](https://github.com/exinori/DCFR-SOLVER) のコミット `4ade6a9e15a841c41867afde1258b9d110cd6fb1` を使用し、全員のスタックを20BBにし、固定OOP補正を廃止します。再学習ではプリフロップと限定したFlop/Turn/Riverを一緒に学習し、seed42・73・101それぞれの3,000万/6,000万/1億2,000万iterationを比較します。生成した戦略データは全ての浅い履歴と頻出の深い履歴を抽出して、このリポジトリに保存します。ゲーム中のアクションではサーバーや再学習は不要です。

**学習モデル：** 各ストリートでCheck、1/3・3/4 POT Bet、All-in、Call、Fold、最大1段のRaiseを学習します。signed external-sampling MCCFRを使い、相手actionのsampling importance補正とown-reachを含む平均戦略を計算します。iteration内のpolicyは凍結します。preflop/postflopとも169 rank/suited identityを保持し、postflop private keyはboard-relative made/draw、overcard/kicker、flush/backdoor、nut blockerを保持し、public keyはpot/各stack/SPR/pot odds/bet比、位置、betting rights、preflop pot typeをまとめます。exact public history全体と1326 suit comboは保存しません。戦略の判断には相手の非公開カードと未来ボードを使いません。固定position tax、手書きrange、hand-specific rule、頻度の事後補正はありません。

**診断：** 凍結した平均戦略に対してBTN AQo/AA/A5s/22/Q5o、UTG2BB→BTN53s/AQoの各action EVをBBで測ります。相手rangeはprior public actionで条件付け、action間でdeal/runout/RNGを共有します。mean/SE/95%区間、paired jam差、全169ハンドのposition別open/shove、9条件ablation、seed/iteration差、per-infoset deltaを公開します。これはNashConvではありません。


**精度の範囲：** 独立seed・学習量・全169ハンド・suited/offsuit・位置・20BBとblind・損益・JSON/UI対応を検証しています。6人・imperfect-recall abstractionでの安定性を検査したもので、全NLHEのNash収束やGTO Wizardと同等の精度を証明したものではありません。6人でのCFRのNash収束は一般には保証されません（[Brown & Sandholm, Science 2019](https://doi.org/10.1126/science.aay2400)）。実ゲームのポストフロップCPUと表にないプリフロップは簡易レンジと最大1,000回のモンテカルロ持分推定を使います。アクション別EVの表示ではありません。CPUの行動前は1.4〜2.3秒待ちます。

[全ハンドの頻度・比較実験・検証](analysis/preflop_model_fix.md) と [固定OOP補正の比較](analysis/tax_sensitivity.md) を公開しています。

## 公開・再計算

`main` に反映するとGitHub ActionsがGitHub Pagesへデプロイします。ソルバーの再計算はリポジトリの **Actions → Train rich NLHE continuation and measure convergence → Run workflow** から開始できます。ジョブは30M/60M/120MのRFI、policy、action EVとraw preflop blueprintをartifactとして出力します。finalize workflowは指定runの3seed・iteration比較と回帰テストを検証し、`preflop_charts.json` と `preflop_policy.json` を更新して公開します。

ローカル再現：pinned upstreamをclone/check outし、`python3 tools/patch_solver.py solver/src`。Rustの`cargo test --release --lib --manifest-path solver/Cargo.toml preflop::`を通してから学習してください。`POKER_MODEL=full`が既定です。ablationは`legacy/nojam/raw/signed/rich/raises/full/chance/sizes`。詳しいCLI・seed・budgetはworkflowに固定しています。Actionsでは一時runnerの不要SDKを削除し40GiB swapを用意します。これはprivate identityを削る代わりに計算時間とdiskを増やすためで、ローカルでは十分なRAM/swapを用意してください。

`index.html`、`preflop_charts.json`、`preflop_policy.json`を同じディレクトリに配置してください。`file://` で直接開いた際にJSONの読み込みが制限されるブラウザーでは、計算済み戦略を使えず簡易判断に切り替わります。
