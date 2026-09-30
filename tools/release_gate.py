"""Gate publication on measured, generic frozen-policy EV inconsistencies.

This is a family-wise Monte Carlo diagnostic, not a NashConv/GTO certificate.
It never changes action probabilities and contains no hand-specific thresholds.
"""
import argparse,json,math
from pathlib import Path
from statistics import NormalDist

SEEDS=(42,73,101)

def release_gate(action_ev,alpha=.05,tolerance_bb=.05):
    expected=[f'seed{seed}-120m' for seed in SEEDS]
    missing=[key for key in expected if key not in action_ev]
    if missing:
        return {'ready':False,'reason':'missing final seed diagnostics','missing':missing}
    rows=[]
    for key in expected:
        spots=action_ev[key]
        if not spots:
            return {'ready':False,'reason':'empty final diagnostics','checkpoint':key}
        for spot in spots:
            actions=spot['actions']
            if not actions or abs(sum(a['probability'] for a in actions)-1)>1e-4:
                raise ValueError('Invalid diagnostic action probabilities')
            for a in actions:
                if a.get('samples',0)<10000:
                    raise ValueError('Insufficient diagnostic samples')
                for field in ['probability','mean_bb','se_bb','estimated_regret_bb','regret_se_bb']:
                    if not math.isfinite(a[field]):
                        raise ValueError('Non-finite diagnostic '+field)
                if not 0<=a['probability']<=1 or a['se_bb']<0 or a['regret_se_bb']<0:
                    raise ValueError('Invalid diagnostic probability/error')
                rows.append((key,spot,a))
    z=NormalDist().inv_cdf(1-alpha/(2*len(rows)))
    failures=[]
    for key,spot,a in rows:
        advantage=a['estimated_regret_bb'];se=a['regret_se_bb']
        low,high=advantage-z*se,advantage+z*se
        reason=None
        if low>tolerance_bb:
            reason='significantly profitable one-step deviation from frozen average policy'
        elif a['probability']>.05 and high < -tolerance_bb:
            reason='materially played action has significantly negative advantage'
        if reason:
            failures.append({'checkpoint':key,'spot':spot['spot'],'hand':spot['hand'],
                'action':a['action'],'probability':a['probability'],'advantage_bb':advantage,
                'se_bb':se,'simultaneous_ci_bb':[low,high],'reason':reason})
    return {'ready':not failures,'familywise_alpha':alpha,'comparisons':len(rows),'z':z,
        'tolerance_bb':tolerance_bb,'failures':failures,
        'limitation':'Bonferroni normal-approximation intervals for sampled spots only; no model-error, full best-response or Nash-convergence certificate.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('quality',type=Path);args=p.parse_args()
    quality=json.loads(args.quality.read_text())
    result=release_gate(quality.get('action_ev',{}));print(json.dumps(result,indent=2))
    if not result['ready']:
        raise SystemExit('Publication blocked: missing or inconsistent final EV evidence.')

if __name__=='__main__':main()
