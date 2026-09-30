"""Validate and publish exact joint-CFR Actions artifacts."""
import csv
import hashlib
import json
import re
import shutil
from pathlib import Path
from analyze_preflop_charts import report
from validate_preflop import check_chart, check_policy, compare

RUNS=Path('runs')
FINAL=RUNS/'joint-cfr-final-seed42-60m'
SEED=RUNS/'joint-cfr-final-seed73-60m'
HALF=RUNS/'joint-cfr-final-seed42-30m'
RAW=RUNS/'raw'
FIXED=RUNS/'fixed-open'
POS=['UTG RFI','HJ RFI','CO RFI','BTN RFI','SB RFI']

def main():
    final,seed,half=(report(p/'chart.json') for p in [FINAL,SEED,HALF])
    for data,path in [(final,FINAL),(seed,SEED),(half,HALF)]:
        check_chart(data)
        check_policy(path/'policy.json',data)
    quality={
        'training_run_id':36649555305,'selected_seed':42,'iterations':60000000,
        'model_sha256':hashlib.sha256(Path('tools/continuation.rs').read_bytes()).hexdigest(),
        'rfi':{p:{'open':final[p]['open'],'limp':final[p]['limp']} for p in POS},
        'seed_stability':compare(final,seed,'independent seed at 60m'),
        'iteration_stability':compare(final,half,'30m versus 60m, seed42'),
        'range_caveats':[]}
    for p,low,high in [('UTG RFI',.10,.25),('HJ RFI',.12,.30),('CO RFI',.18,.40),('BTN RFI',.33,.60)]:
        if not low<=final[p]['open']<=high:
            quality['range_caveats'].append(p+': outside loose external prior; no identical independent benchmark')
    Path('analysis/runs').mkdir(parents=True,exist_ok=True)
    for path,name in [(SEED,'seed73-60m'),(HALF,'seed42-30m')]:
        shutil.copyfile(path/'chart.json',Path('analysis/runs')/(name+'.json'))
    shutil.copyfile(FINAL/'chart.json','preflop_charts.json')
    shutil.copyfile(FINAL/'policy.json','preflop_policy.json')
    Path('analysis/quality.json').write_text(json.dumps(quality,indent=2))
    raw=report(RAW/'chart.json')
    fixed=report(FIXED/'chart.json')
    datasets=[('raw-mixed-open',42,30000000,raw),('cfr-fixed-2.5bb-diagnostic',42,30000000,fixed),
        ('joint-final',42,30000000,half),('joint-final',42,60000000,final),('joint-final',73,60000000,seed)]
    with Path('analysis/final_frequency_169.csv').open('w',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['model','seed','iterations','position','hand','combos','fold','raise_2bb','raise_2_5bb','raise_3bb','allin','limp','open'])
        for model,s,n,data in datasets:
            for p in POS:
                for h in data[p]['hands']:
                    a=h['actions']
                    writer.writerow([model,s,n,p,h['hand'],h['combos'],a.get('fold',0),a.get('raise 4',0),
                        a.get('raise 5',0),a.get('raise 6',0),a.get('allin',0),h['limp'],h['open']])
    lines=['\n## 最終学習と全169クラスの比較\n',
        '公開データはseed42・6,000万iteration。[全169ハンド×5位置の各行動頻度と比較条件](final_frequency_169.csv)、[検証の数値](quality.json)を保存した。',
        '\n| 条件 | UTG | HJ/MP | CO | BTN | SB raise/shove | SB limp |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for name,s,n,data in datasets:
        lines.append('| '+f'{name}, seed{s}, {n//1000000}m'+' | '+' | '.join(f"{data[p]['open']:.1%}" for p in POS)+f" | {data['SB RFI']['limp']:.1%} |")
    lines.extend(['\nraw比較は同じ20BB・seed42・30m・2/2.5BB＋open shove・1 board sampleで、終端だけをraw showdownに戻したもの。fixed-2.5bbはベット額の診断用旧版CFRで、最終版のマルチウェイ順/最小ベット修正前。最終版との全差をベット額だけに帰属させない。',
        '\n| 位置 | seed差の加重RMS | seed差の総open差 | 学習量差の加重RMS | 学習量差の総open差 |',
        '| --- | ---: | ---: | ---: | ---: |'])
    for p in POS:
        a=quality['seed_stability'][p];b=quality['iteration_stability'][p]
        lines.append(f"| {p} | {a['combo_weighted_rms']:.3f} | {a['total_open_difference']:.1%} | {b['combo_weighted_rms']:.3f} | {b['total_open_difference']:.1%} |")
    lines.append('\nRMSは1,326コンボで加重した各ハンドopen頻度の差。sanity checkはRMS≤0.16・総open差≤8ポイント、premium/weak、suited/offsuit、位置、確率、20BBとblindを検査する。これは精度やNash収束の証明ではない。境界ハンドに残る揺れもCSVで確認できる。')
    if quality['range_caveats']:
        lines.append('\n外部の条件が違う参考範囲から外れた位置：'+', '.join(quality['range_caveats'])+'。頻度を参考範囲へ強制補正していない。')
    for p,names in [('BTN RFI','32o 54o 65o 76o T5o J2o J5o Q2o Q5o Q8o K2o A2o 22 A5s Q5s'.split()),
        ('UTG RFI','22 55 77 99 JTs QJs KJs A5s A9s AJo AQo AKs AKo'.split())]:
        rows={h['hand']:h for h in final[p]['hands']}
        lines.extend(['\n### '+p,'\n| ハンド | Fold | 2BB Raise | 2.5BB Raise | Shove |','| --- | ---: | ---: | ---: | ---: |'])
        for name in names:
            a=rows[name]['actions']
            lines.append('| '+name+' | '+' | '.join(f"{a.get(k,0):.1%}" for k in ['fold','raise 4','raise 5','allin'])+' |')
    lines.append('\n### 計算時間と検証\n')
    for path,label in [(RAW,'raw / 30m'),(HALF,'joint / 30m'),(FINAL,'joint / 60m'),(SEED,'joint seed73 / 60m')]:
        log=(path/'training.log').read_text()
        elapsed=re.search(r'Elapsed \(wall clock\) time.*?: (.+)',log)
        memory=re.search(r'Maximum resident set size \(kbytes\): (\d+)',log)
        if memory: lines.append(f"- {label}: 時間 {elapsed.group(1) if elapsed else 'log参照'}, 最大RSS {int(memory.group(1))/1024:.0f} MiB。")
    lines.append('\nQ5o bucket139、UTG→MP→CO Fold後のBTN履歴、2/2.5BBとAll-inのaction order、export確率合計、通常位置RFIにCall/Limpがないこと、全員20BB・SB0.5BB/BB1BB、損益保存、未来カードを特徴に入れないこと、キッカー、マルチウェイ応答順、最小1BBベットを自動検証した。')
    doc=Path('analysis/preflop_model_fix.md')
    base=doc.read_text().split('\n## 最終学習と全169クラスの比較')[0]
    doc.write_text(base+'\n'.join(lines)+'\n')
    html=Path('index.html').read_text()
    html=html.replace("fetch('./preflop_charts.json')","fetch('./preflop_charts.json?v=joint-final60m-20260930')")
    html=html.replace("fetch('./preflop_policy.json')","fetch('./preflop_policy.json?v=joint-final60m-20260930')")
    marker="openingCharts=new Map(spots.map(s=>[s.spot_name,new Map(s.hands.map(h=>[h.hand,h.actions]))]));"
    addition="const rootActions=spots.find(s=>s.spot_name==='UTG RFI').hands.find(h=>h.actions?.length)?.actions||[],rootSizes=rootActions.filter(a=>a.action.startsWith('raise ')).map(a=>Number(a.action.slice(6)));if(rootSizes.length)solverRaiseSizes[0]=rootSizes;if(rootActions.some(a=>a.action==='allin'))solverMinAllinDepth=0;"
    if addition not in html: html=html.replace(marker,marker+addition)
    html=html.replace('参考戦略（簡略ゲームの計算値）','参考戦略（20BB・近似計算）')
    html=html.replace('depth=game.solverDepth,options=[];','depth=game.solverDepth,options=[],mayRaise=!game.acted.has(p.id);')
    html=html.replace('for(const raiseTo of raiseTos)if(raiseTo-game.currentBet','for(const raiseTo of raiseTos)if(mayRaise&&raiseTo-game.currentBet')
    html=html.replace('for(const raiseTo of raiseTos)if(raiseTo>p.streetBet','for(const raiseTo of raiseTos)if(mayRaise&&raiseTo>p.streetBet')
    html=html.replace("if(depth>=solverMinAllinDepth)options.push({kind:'allin'})","if(mayRaise&&depth>=solverMinAllinDepth)options.push({kind:'allin'})")
    html=html.replace('プリフロップ計算はフロップ以降のプレーを簡略化しており、実際の全局面のGTOやアクション別EVを保証しません。',
        'プリフロップ戦略は、ベット額と役・ドローをまとめたFlop/Turn/RiverもCFRで学習しています。実ゲームのポストフロップCPUは簡易推定です。全局面のGTOやアクション別EVを保証しません。')
    Path('index.html').write_text(html)

    readme=Path('README.md').read_text()
    readme=readme.replace('オープン2.5BB（SBは3BB）','オープン2BB・2.5BB（SBは3BB）')
    readme=readme.replace('以降オールインです','オープンを含むオールインです')
    marker=chr(96)+'.github/workflows/train-preflop.yml'+chr(96)+' でスタックを20BBに変更して3,000万回学習します。'
    readme=readme.replace(marker,'全員のスタックを20BBにし、固定OOP補正を廃止します。再学習ではプリフロップと限定したFlop/Turn/Riverを一緒に学習し、seed42の3,000万/6,000万iterationとseed73の6,000万iterationを比較します。')
    start=readme.find('**学習モデル：**')
    if start<0: start=readme.index('**精度の範囲：**')
    end=readme.index('\n\n## 公開',start)
    readme=readme[:start]+'''**学習モデル：** 各ストリートでCheck、1/3・3/4 POT Bet、All-in、Call、Foldの確率をCFRで学習します。postflop raiseは省略し、役・ドロー・盤面・位置・相手位置・SPR・pot typeを情報集合へまとめます。相手の非公開カードと未来ボードを判断に使わず、RFIレンジの手書きやQ5oの例外処理もありません。

**精度の範囲：** 独立seed・学習量・全169ハンド・suited/offsuit・位置・20BBとblind・損益・JSON/UI対応を検証しています。全NLHEのNash収束やGTO Wizardと同等の精度を証明したものではありません。6人でのCFRのNash収束は一般には保証されません（[Brown & Sandholm, Science 2019](https://doi.org/10.1126/science.aay2400)）。実ゲームのポストフロップCPUと表にないプリフロップは簡易レンジと最大1,000回のモンテカルロ持分推定を使います。アクション別EVの表示ではありません。CPUの行動前は1.4〜2.3秒待ちます。

[全ハンドの頻度・比較実験・検証](analysis/preflop_model_fix.md) と [固定OOP補正の比較](analysis/tax_sensitivity.md) を公開しています。'''+readme[end:]
    readme=readme.replace('Train 6-max 20BB preflop blueprint','Train and validate 6-max 20BB strategy')
    Path('README.md').write_text(readme)
    workflow=Path('.github/workflows/experiment-joint-cfr.yml').read_text()
    workflow=workflow.replace('name: Learn bounded postflop continuation','name: Train and validate 6-max 20BB strategy',1)
    a=workflow.index('  push:');b=workflow.index('  workflow_dispatch:',a)
    workflow=workflow[:a]+workflow[b:]
    workflow+='''
  validate:
    needs: train
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          pattern: joint-cfr-final-*
          path: runs
      - name: Compare seed and learning length
        run: |
          python3 tools/validate_preflop.py runs/joint-cfr-final-seed42-60m/chart.json --policy runs/joint-cfr-final-seed42-60m/policy.json --seed runs/joint-cfr-final-seed73-60m/chart.json --half runs/joint-cfr-final-seed42-30m/chart.json --output runs/quality.json
      - uses: actions/upload-artifact@v4
        with:
          name: validated-preflop-strategy-20bb
          path: |
            runs/joint-cfr-final-seed42-60m/chart.json
            runs/joint-cfr-final-seed42-60m/policy.json
            runs/quality.json
'''
    Path('.github/workflows/train-preflop.yml').write_text(workflow)
    pages=Path('.github/workflows/pages.yml').read_text()
    marker='      - name: Configure Pages'
    check='''      - name: Verify strategy and UI
        run: |
          python3 tools/test_preflop_export.py
          python3 tools/validate_preflop.py preflop_charts.json --policy preflop_policy.json --seed analysis/runs/seed73-60m.json --half analysis/runs/seed42-30m.json
          node tools/test_preflop_frontend.cjs
'''
    if 'Verify strategy and UI' not in pages: pages=pages.replace(marker,check+marker)
    Path('.github/workflows/pages.yml').write_text(pages)
    print(json.dumps(quality,indent=2))

if __name__=='__main__':
    main()
