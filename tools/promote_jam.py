"""Publish measured strategies, not calibrated ranges. Run after all artifacts arrive."""
import argparse,csv,json,shutil,hashlib,re
from pathlib import Path
from analyze_preflop_charts import report
from analyze_jam import policy_delta,ev_summary
from validate_preflop import check_chart,check_policy,compare
from check_convergence import warnings

POS=['UTG RFI','HJ RFI','CO RFI','BTN RFI','SB RFI']

def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,indent=2))

def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(map(str,r))+' |' for r in rows])

def main():
    p=argparse.ArgumentParser();p.add_argument('runs',type=Path);p.add_argument('ablation',type=Path);p.add_argument('--control',type=Path);p.add_argument('--training-source',required=True);args=p.parse_args()
    out=Path('analysis/jam');out.mkdir(parents=True,exist_ok=True)
    final=args.runs/'jam-final-seed42'; charts=report(final/'120m-chart.json');check_chart(charts)
    check_policy(final/'120m-policy.json',charts)
    quality={'conditions':{'players':6,'effective_stack_bb':20,'sb_bb':.5,'bb_bb':1,'ante':0,'rake':0},'model_sha256':hashlib.sha256(Path('tools/continuation.rs').read_bytes()).hexdigest(),
             'seed_stability':{},'iteration_stability':{},'resources':{},'policy_deltas':{},'action_ev':{},'ablation':{},'training_source_commit':args.training_source,'nashconv':None,'nashconv_reason':'Conditional one-step deviations only; not a full best response or exploitability certificate.'}
    for seed in [42,73,101]:
        folder=args.runs/f'jam-final-seed{seed}'
        log=(folder/'training.log').read_text()
        rss=re.search(r'Maximum resident set size \(kbytes\): (\d+)',log)
        elapsed=re.search(r'Elapsed \(wall clock\) time .*?: (.+)',log)
        quality['resources'][str(seed)]={'max_rss_kb':int(rss.group(1)) if rss else None,'elapsed':elapsed.group(1) if elapsed else None}
        shutil.copy(folder/'training.log',out/f'seed{seed}-training.log')
        for length in [30,60,120]:
            chart=folder/f'{length}m-chart.json';policy=folder/f'{length}m-policy.json';ev=folder/f'{length}m-ev.json'
            check_chart(report(chart));check_policy(policy,report(chart))
            dest=out/f'seed{seed}-{length}m';dest.mkdir(exist_ok=True)
            for source in [chart,policy,ev,folder/f'{length}m-frequency.json',folder/f'{length}m-frequency.csv']:
                if source.exists():shutil.copy(source,dest/source.name)
            quality['action_ev'][f'seed{seed}-{length}m']=ev_summary(ev)
            quality.setdefault('convergence_warnings',{})[f'seed{seed}-{length}m']=warnings(quality['action_ev'][f'seed{seed}-{length}m'])
        if seed!=42:
            quality['seed_stability'][str(seed)]=compare(charts,report(folder/'120m-chart.json'),'seed')
            quality['policy_deltas'][f'42-vs-{seed}']=policy_delta(final/'120m-policy.json',folder/'120m-policy.json')
        for a,b in [(30,60),(60,120)]:
            quality['iteration_stability'][f'{seed}:{a}-{b}']=compare(report(folder/f'{b}m-chart.json'),report(folder/f'{a}m-chart.json'),'iteration')
            quality['policy_deltas'][f'{seed}:{a}-{b}']=policy_delta(folder/f'{a}m-policy.json',folder/f'{b}m-policy.json')
    for folder in sorted(args.ablation.glob('jam-*-seed42-30m')):
        mode=folder.name.removeprefix('jam-').removesuffix('-seed42-30m');dest=out/'ablation'/mode;dest.mkdir(parents=True,exist_ok=True)
        for source in folder.iterdir():
            if source.suffix in ['.json','.csv','.log']:shutil.copy(source,dest/source.name)
        frequency=report(folder/'chart.json')
        quality['ablation'][mode]={'rfi':{pos:{'open':info['open'],'jam':sum(h['combos']*h['actions'].get('allin',0) for h in info['hands'])/1326} for pos,info in frequency.items()},'ev':ev_summary(folder/'ev.json')}
    if set(quality['ablation'])!={'legacy','nojam','raw','signed','rich','raises','full','chance','sizes'}:raise ValueError('Missing required matched ablation')
    if args.control:
        quality['unclip_only']=ev_summary(args.control/'ev.json');shutil.copytree(args.control,out/'unclip-only',dirs_exist_ok=True)
    shutil.copy(final/'120m-chart.json','preflop_charts.json');shutil.copy(final/'120m-policy.json','preflop_policy.json')
    release_policy=json.loads(Path('preflop_policy.json').read_text());release_policy['training_source_commit']=args.training_source;release_policy['training_seed']=42;release_policy['sb_bb']=.5;release_policy['bb_bb']=1
    Path('preflop_policy.json').write_text(json.dumps(release_policy,separators=(',',':')))
    # Complete per-infoset metrics are stored separately to keep the summary usable.
    deltas=quality.pop('policy_deltas');write(out/'policy_deltas.json',deltas)
    quality['policy_delta_summary']={k:{x:v[x] for x in ['histories_left','histories_right','histories_shared','infosets','mean_l1','max_action_delta']} for k,v in deltas.items()}
    write(Path('analysis/quality.json'),quality)
    write(out/'quality.json',quality)
    with (out/'frequency_169.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['position','hand','combos','open','limp','fold','raise2','raise2.5','allin'])
        for pos,info in charts.items():
            for h in info['hands']:w.writerow([pos,h['hand'],h['combos'],h['open'],h['limp'],*[h['actions'].get(a,0) for a in ['fold','raise 4','raise 5','allin']]])
    old=json.loads(Path('analysis/old_spots.json').read_text())
    lines=[Path('analysis/jam_method.md').read_text(),'\n## 最終学習と比較結果\n','seed42/73/101で同じモデルを120Mまで学習。30M/60M/120Mは各seedの同一RNG軌跡から保存した。頻度の事後補正・ハンド例外はない。\n']
    lines+=['### 計算資源\n',table(['seed','120M+checkpoint EV wall time','max RSS GiB'],[[seed,v['elapsed'],f"{v['max_rss_kb']/1048576:.2f}" if v['max_rss_kb'] else 'unknown'] for seed,v in quality['resources'].items()])]
    latest=quality['action_ev']['seed42-120m']
    rows=[]
    for s in latest:
        for a in s['actions']:rows.append([s['spot'],s['hand'],a['action'],f"{100*a['probability']:.2f}%",f"{a['mean_bb']:.4f}",f"{a['se_bb']:.4f}",a['samples'],f"{a['estimated_regret_bb']:.4f}",f"{a.get('stored_cumulative_regret_half_bb',0):.1f}",f"{100*a.get('current_regret_matching_probability',0):.2f}%"])
    lines+=['### 各actionの推定EV（BB）\n',table(['spot','hand','action (half-BB chips)','frequency','mean EV','SE','n','estimated advantage','stored cumulative regret (halfBB)','current π'],rows),'\n95%区間は各平均 ± 1.96×SE。全て凍結平均戦略に対する条件付き評価であり、累積regretログそのものではない。同じdeal/runout/RNGをaction間で共有し、相手のprior public actionでrangeを条件付けた。paired jam差・SEはEV JSON参照。標準誤差は固定された学習戦略内のMonte Carlo誤差のみで、モデル誤差やseed差を含まない。\n']
    rows=[]
    for s in latest:
        key=s['spot']+' '+s['hand'];before=old.get(key,{})
        for a in s['actions']:rows.append([s['spot'],s['hand'],a['action'],f"{100*before.get(a['action'],0):.2f}%",f"{100*a['probability']:.2f}%"])
    lines+=['### 旧mainとの頻度比較\n',table(['spot','hand','action','old main','new seed42 120M'],rows)]
    if 'unclip_only' in quality:
        control_rows=[]
        for spot in quality['unclip_only']:
            if spot['hand'] in ['AQo','53s']:
                for a in spot['actions']:control_rows.append([spot['spot'],spot['hand'],a['action'],f"{100*a['probability']:.3f}%",f"{a['mean_bb']:.4f}",f"{a['se_bb']:.4f}"])
        lines+=['### Clippingだけを外した追加control（同一chance stream）\n',table(['spot','hand','action','frequency','EV BB','SE BB'],control_rows)]
    rows=[]
    for mode,v in quality['ablation'].items():
        aq=next(s for s in v['ev'] if s['spot']=='BTN RFI' and s['hand']=='AQo');weak=next(s for s in v['ev'] if s['hand']=='53s');getjam=lambda s:next((a['probability'] for a in s['actions'] if a['action']=='allin'),0)
        rows.append([mode,*[f"{100*v['rfi'][pos]['open']:.2f}%" for pos in POS],f"{100*getjam(aq):.2f}%",f"{100*getjam(weak):.2f}%",f"{aq['jam_minus_best_small_bb']:.3f}" if aq['jam_minus_best_small_bb'] is not None else 'n/a'])
    lines+=['\n### 同一seed42・30Mの9条件ablation\n',table(['model',*POS,'AQo jam','53s jam','AQo jam-small EV BB'],rows),'\n全169ハンド・position別open/shove率・主要hand EVは `jam/ablation/*/frequency.json` と `ev.json` に保存。raw/nojamは旧clipped algorithmも維持し、signedはsigned regret+importance averagingを併用する。richer/raiseの相互作用をfullで確認する。chanceは2board/iterationなので同じiterationでも約2倍のchance作業量。sizesは3bet5/7BB、4bet jamのみ。\n']
    rows=[]
    for seed in [42,73,101]:
        for length in [30,60,120]:
            vv=quality['action_ev'][f'seed{seed}-{length}m'];aq=next(s for s in vv if s['spot']=='BTN RFI' and s['hand']=='AQo');weak=next(s for s in vv if s['hand']=='53s');jam=lambda s:next(a['probability'] for a in s['actions'] if a['action']=='allin');rows.append([seed,f'{length}M',f'{100*jam(aq):.2f}%',f'{100*jam(weak):.2f}%',f"{aq['jam_minus_best_small_bb']:.3f}",f"{aq['one_step_deviation_gain_bb']:.3f}"])
    lines+=['### Seed差とiteration差\n',table(['seed','iterations','AQo jam','53s jam','AQo jam-small EV','AQo one-step gain'],rows), '\n全infoset L1差は `jam/policy_deltas.json`、全positionのRFI RMS差は `quality.json` 参照。混合action頻度の変化はEVがほぼ同じ場合も起こる。1局面のone-step gainはNashConvやexploitabilityではない。\n']
    warnings_rows=[[key,w['spot'],w['hand'],w.get('action',''),w['reason']] for key,v in quality['convergence_warnings'].items() for w in v]
    lines+=['### Convergence warnings（頻度を変更しない診断）\n',table(['checkpoint','spot','hand','action','warning'],warnings_rows) if warnings_rows else 'Material average probabilityと有意な負advantageの組合せは、指定spotでは検出されなかった。これは全ゲームの収束証明ではない。']
    rows=[]
    selected={'BTN RFI':['32o','54o','65o','76o','T5o','J2o','J5o','Q2o','Q5o','Q8o','K2o','A2o','22','A5s','Q5s','AA','AQo'],'UTG RFI':['22','55','77','99','JTs','QJs','KJs','A5s','A9s','AJo','AQo','AKs','AKo']}
    for pos,labels in selected.items():
        for label in labels:
            h=next(h for h in charts[pos]['hands'] if h['hand']==label);rows.append([pos,label,*[f"{100*h['actions'].get(a,0):.2f}%" for a in ['fold','raise 4','raise 5','allin']]])
    lines+=['### 境界hand・premium hand\n',table(['position','hand','Fold','2BB','2.5BB','jam'],rows)]
    Path('analysis/preflop_model_fix.md').write_text('\n\n'.join(lines))
    Path('analysis/continuation_evaluation.md').write_text('# Continuation evaluation\n\n旧ヒューリスティックの値は現行モデルのEVではありません。現行の凍結平均戦略を条件付きdealで評価したaction EV、95% CI、paired difference、seed/iteration比較を [preflop_model_fix.md](preflop_model_fix.md) と [jam/quality.json](jam/quality.json) に保存しています。\n\n推定EVは各postflop opponentのprivate cardを戦略判断から隠しています。NashConvは未計算です。全6人NLHEの高精度GTOの証明はありません。\n')
    print(json.dumps({k:quality[k] for k in ['seed_stability','iteration_stability','policy_delta_summary']},indent=2))

if __name__=='__main__':main()
