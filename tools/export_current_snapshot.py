"""Export an explicitly requested, unconverged snapshot without frequency edits."""
import json,shutil,hashlib,csv,math
from pathlib import Path
from statistics import NormalDist
from analyze_preflop_charts import report
from analyze_jam import ev_summary,policy_delta
from validate_preflop import check_chart,check_policy,compare
from check_convergence import warnings

SOURCES={42:(80,36721624956),73:(95,36789601087),101:(84,36789601087)}
CORE=['continuation.rs','continuation_legacy.rs','upgrade_solver.py','patch_solver_base.py','add_resumable_solver.py','trainer_checkpoint.rs']
SHA='679913ade0d3a19e10573c5a9f7b7636d5bb2a3b'
VERSION='experimental-v8-snapshot-20261001'
def write(path,data):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(data,indent=2))
def table(head,rows):
    return '\n'.join(['| '+' | '.join(head)+' |','|'+'|'.join(['---']*len(head))+'|']+['| '+' | '.join(map(str,r))+' |' for r in rows])
def main():
    out=Path('analysis/current_snapshot');out.mkdir(parents=True,exist_ok=True)
    q={'release_kind':'experimental-unconverged','user_requested_stop':'2026-10-01 19:21 JST','training_source_commit':SHA,
       'published_seed':42,'published_iterations':80000000,'checkpoints':{},'action_ev':{},'warnings':{},'stability':{},
       'source_sha256':{f'tools/{p}':hashlib.sha256(Path('tools',p).read_bytes()).hexdigest() for p in CORE},
       'conditions':{'players':6,'effective_stack_bb':20,'sb_bb':.5,'bb_bb':1,'ante':0,'rake':0},
       'gto_certified':False,'postflop_cpu':'simplified runtime policy; joint training policy not exported'}
    charts={}
    for seed,(length,run) in SOURCES.items():
        raw=Path('raw',str(seed))
        manifest=dict((line.split(maxsplit=1)[1].strip(),line.split()[0]) for line in (raw/'source-sha256.txt').read_text().splitlines())
        for name,h in q['source_sha256'].items():
            if manifest.get(name)!=h:raise ValueError('source mismatch '+name)
        if (raw/'source-commit.txt').read_text().strip()!=SHA:raise ValueError('source commit mismatch')
        chart=raw/f'{length}m-chart.json';ev=raw/f'{length}m-ev.json';blue=raw/f'{length}m-blueprint.bin'
        assert chart.exists() and ev.exists() and blue.exists()
        charts[seed]=report(chart)
        try:check_chart(charts[seed])
        except ValueError as e:q.setdefault('sanity_warnings',{})[str(seed)]=str(e)
        check_policy(raw/'final-policy.json',charts[seed])
        folder=out/f'seed{seed}-{length}m';folder.mkdir(exist_ok=True)
        for source in [chart,ev,raw/'final-policy.json',raw/'final-frequency.json',raw/'source-sha256.txt',raw/'source-commit.txt',raw/'training.log']:
            shutil.copy(source,folder/source.name)
        key=f'seed{seed}-{length}m';q['checkpoints'][str(seed)]={'iterations':length*1000000,'run_id':run,'artifact':f'measurements-{length*1000000}-seed{seed}'}
        q['action_ev'][key]=ev_summary(ev);q['warnings'][key]=warnings(q['action_ev'][key])
        baseline=Path('raw',f'60-{seed}','60m-chart.json')
        try:q['stability'][f'{seed}:60-{length}']=compare(charts[seed],report(baseline),'iteration')
        except ValueError as e:q['stability'][f'{seed}:60-{length}']={'failed':str(e)}
        q.setdefault('policy_deltas',{})[f'{seed}:60-{length}']=policy_delta(Path('raw',f'60-{seed}','final-policy.json'),raw/'final-policy.json')
    for seed in [73,101]:
        try:q['stability'][f'42-vs-{seed}']=compare(charts[42],charts[seed],'different seeds AND unequal iterations')
        except ValueError as e:q['stability'][f'42-vs-{seed}']={'failed':str(e)}
    comparisons=[]
    for key,spots in q['action_ev'].items():
        for spot in spots:
            assert abs(sum(a['probability'] for a in spot['actions'])-1)<1e-4
            for a in spot['actions']:
                assert a['samples']>=10000
                assert all(math.isfinite(a[f]) for f in ['probability','mean_bb','se_bb','estimated_regret_bb','regret_se_bb'])
                assert 0<=a['probability']<=1 and a['se_bb']>=0 and a['regret_se_bb']>=0
                comparisons.append((key,spot,a))
    z=NormalDist().inv_cdf(1-.05/(2*len(comparisons)));fail=[]
    for key,s,a in comparisons:
        lo=a['estimated_regret_bb']-z*a['regret_se_bb'];hi=a['estimated_regret_bb']+z*a['regret_se_bb']
        if lo>.05 or (a['probability']>.05 and hi<-.05):
            fail.append({'checkpoint':key,'spot':s['spot'],'hand':s['hand'],'action':a['action'],'probability':a['probability'],'advantage_bb':a['estimated_regret_bb'],'se_bb':a['regret_se_bb'],'simultaneous_ci_bb':[lo,hi]})
    q['snapshot_ev_diagnostic']={'ready':not fail,'comparisons':len(comparisons),'familywise_alpha':.05,'z':z,'tolerance_bb':.05,'failures':fail}
    q['release_gate']={'ready':False,'reason':'120M three-seed converged release not completed; user requested current experimental snapshot'}
    for src,dst in [('80m-chart.json','preflop_charts.json'),('final-policy.json','preflop_policy.json')]:shutil.copy(Path('raw','42',src),dst)
    q['artifact_sha256']={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['preflop_charts.json','preflop_policy.json']}
    write(out/'policy_deltas.json',q.pop('policy_deltas'));write('analysis/quality.json',q)
    rows=[];old=json.loads(Path('analysis/old_spots.json').read_text())
    for spot in q['action_ev']['seed42-80m']:
        for a in spot['actions']:
            rows.append([spot['spot'],spot['hand'],a['action'],f"{100*old.get(spot['spot']+' '+spot['hand'],{}).get(a['action'],0):.3f}%",f"{100*a['probability']:.3f}%",f"{a['mean_bb']:.5f}",f"{a['se_bb']:.5f}",a['samples']])
    lines=['# 保存済みv8戦略の実験版','2026-10-01、ユーザー指示で追加学習を停止。公開戦略は事前に主系列としたseed42の80Mをそのまま使用。seed73は95M、seed101は84M。頻度を編集・平均・補正していない。120M学習・収束確認は完了していない。GTO精度の証明ではない。',Path('analysis/jam_method.md').read_text(),'## 旧mainと公開snapshot・action EV',table(['spot','hand','action','old','snapshot','EV BB','SE BB','N'],rows),'## 複数seed・iteration比較（異なる最終iteration）',json.dumps(q['stability'],indent=2),'## 同時区間によるEV診断',json.dumps(q['snapshot_ev_diagnostic'],indent=2),'## 全seedのEV・警告',json.dumps(q['action_ev'],indent=2),json.dumps(q['warnings'],indent=2),json.dumps(q.get('sanity_warnings',{}),indent=2),'## 限界','全6人NLHEのNashConvは未計算。公開情報・private hand abstraction、有限サイズ、各street最大1段raiseを使用。CPUの実ゲームpostflopは簡易方策。標準誤差はMC誤差のみ。JSONは学習出力をそのままコピー。科学的な正式リリース判定は未通過のまま保存する。']
    Path('analysis/preflop_model_fix.md').write_text('\n\n'.join(lines))
    Path('analysis/continuation_evaluation.md').write_text('# Experimental current snapshot\n\nSee preflop_model_fix.md and quality.json. Training stopped at user request; unconverged, not GTO-certified.\n')
    with (out/'frequency_169.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['position','hand','open','limp','actions'])
        for pos,info in charts[42].items():
            for h in info['hands']:w.writerow([pos,h['hand'],h['open'],h['limp'],json.dumps(h['actions'])])
    html=Path('index.html').read_text().replace('signed-full120m-20260930',VERSION)
    html=html.replace('参考戦略（20BB・近似計算）','参考戦略（20BB・実験版／未収束）')
    html=html.replace('<body>','<body>\n<p style="margin:12px 20px;color:#e4bc72;font-size:12px">戦略は実験版（学習途中・未収束）。GTO精度は未検証です。</p>')
    Path('index.html').write_text(html)
    readme=Path('README.md').read_text()
    readme='> 現在の公開版はユーザー指示により途中学習結果を採用した実験版です。seed42 80Mを使用し、seed73 95M・seed101 84Mと比較しています。120M・収束確認は未完了です。CPU全体をGTOとみなさないでください。\n\n'+readme
    Path('README.md').write_text(readme)
    print(json.dumps(q['snapshot_ev_diagnostic'],indent=2))
if __name__=='__main__':main()
