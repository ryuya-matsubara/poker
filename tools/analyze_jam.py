"""Frozen policy EV and full-distribution deltas. Never changes a strategy."""
import argparse,json,math,csv
from pathlib import Path
from analyze_preflop_charts import report


def policy_delta(left,right):
    a=json.loads(Path(left).read_text())['histories'];b=json.loads(Path(right).read_text())['histories']
    rows=[]
    for h in sorted(a.keys()&b.keys()):
        for i,(x,y) in enumerate(zip(a[h],b[h])):
            if x is None or y is None or len(x)!=len(y):continue
            rows.append({'history':h,'bucket':i,'l1':sum(abs(p-q) for p,q in zip(x,y)),
                         'maximum_action_delta':max(abs(p-q) for p,q in zip(x,y))})
    return {'infosets':len(rows),'mean_l1':sum(r['l1'] for r in rows)/max(1,len(rows)),
            'max_action_delta':max((r['maximum_action_delta'] for r in rows),default=0),'rows':rows}


def ev_summary(path):
    data=json.loads(Path(path).read_text());out=[]
    for spot in data:
        actions=spot['actions'];value=sum(a['probability']*a['mean_bb'] for a in actions)
        best=max(actions,key=lambda a:a['mean_bb']);jam=next((a for a in actions if a['action']=='allin'),None)
        small=max((a for a in actions if a['action'].startswith('raise')),key=lambda a:a['mean_bb'],default=None)
        warnings=[]
        if spot['spot']=='BTN RFI' and spot['hand']=='AQo' and jam and jam['probability']>sum(a['probability'] for a in actions if a['action'].startswith('raise')):
            warnings.append('AQo jam dominates small raise frequency; inspect paired EV difference')
        if spot['spot']=='UTG 2BB -> BTN' and spot['hand']=='53s' and jam and jam['probability']>.02:
            warnings.append('53s material shove probability; this is a diagnostic only')
        out.append({'spot':spot['spot'],'hand':spot['hand'],'policy_ev_bb':value,
                    'best_fixed_action':best['action'],'one_step_deviation_gain_bb':best['mean_bb']-value,
                    'jam_minus_best_small_bb':jam['mean_bb']-small['mean_bb'] if jam and small else None,
                    'paired_se_bb':small.get('jam_difference_se_bb') if small else None,
                    'warnings':warnings,'actions':actions})
    return out


def main():
    p=argparse.ArgumentParser();p.add_argument('ev',type=Path);p.add_argument('--output',type=Path);args=p.parse_args()
    data=ev_summary(args.ev)
    if args.output:args.output.write_text(json.dumps(data,indent=2))
    print(json.dumps(data,indent=2))


if __name__=='__main__':main()
