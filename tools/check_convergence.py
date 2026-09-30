"""Summarize EV uncertainty and convergence warnings without modifying frequencies."""
import argparse,json,math
from pathlib import Path
from analyze_jam import ev_summary,policy_delta
from analyze_preflop_charts import report
from validate_preflop import compare


def warnings(ev):
    out=[]
    for spot in ev:
        for action in spot['actions']:
            if action['probability']>.05 and action.get('estimated_regret_bb',0)+1.96*action.get('regret_se_bb',0)<-.05:
                out.append({'spot':spot['spot'],'hand':spot['hand'],'action':action['action'],
                            'reason':'material average probability with significantly negative frozen-policy advantage',
                            'advantage_bb':action['estimated_regret_bb'],'se_bb':action['regret_se_bb']})
        for message in spot['warnings']:out.append({'spot':spot['spot'],'hand':spot['hand'],'reason':message})
    return out


def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--output',type=Path);args=p.parse_args()
    result={}
    for seed in [42,73,101]:
        folder=args.directory/f'jam-final-seed{seed}'
        for length in [30,60,120]:
            ev=ev_summary(folder/f'{length}m-ev.json');result[f'{seed}:{length}m']={'warnings':warnings(ev),
                'one_step_gain_bb':{s['spot']+' '+s['hand']:s['one_step_deviation_gain_bb'] for s in ev}}
    if args.output:args.output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
