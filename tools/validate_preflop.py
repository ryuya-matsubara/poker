"""Fail closed on malformed or grossly implausible preflop output.

These gates are diagnostics, not a proof of Nash convergence. Independent seeds
and training lengths are compared by --seed and --half.
"""
import argparse
import json
import math
from pathlib import Path

from analyze_preflop_charts import report

POSITIONS = ['UTG RFI', 'HJ RFI', 'CO RFI', 'BTN RFI', 'SB RFI']


def check_chart(data):
    if list(data) != POSITIONS:
        raise ValueError('expected all five RFI positions')
    opening = [data[pos]['open'] for pos in POSITIONS]
    if not all(0.07 < x < 0.65 for x in opening[:4]) or not 0.07 < opening[4] + data['SB RFI']['limp'] < 1:
        raise ValueError(f'implausible RFI totals: {opening}')
    if not all(a <= b + .02 for a, b in zip(opening[:3], opening[1:4])):
        raise ValueError(f'early-to-late ranges do not expand: {opening}')
    # A very narrow BTN range is a known failure of forced-showdown terminals.
    # This is an anomaly gate, not a prescribed hand-by-hand opening chart.
    if data['BTN RFI']['open'] < .33:
        raise ValueError(f'BTN RFI remains abnormally narrow: {data["BTN RFI"]["open"]:.1%}')
    for pos, ceiling in [('UTG RFI',.25),('HJ RFI',.30),('CO RFI',.40)]:
        if data[pos]['open'] > ceiling:
            raise ValueError(f'{pos} remains abnormally wide: {data[pos]["open"]:.1%}')
    for pos, info in data.items():
        h = {row['hand']: row['open'] + row['limp'] if pos == 'SB RFI' else row['open'] for row in info['hands']}
        if pos != 'SB RFI' and info['limp'] > .0001:
            raise ValueError(f'non-SB RFI contains a call/limp: {pos}')
        if h['AA'] < .85 or h['AA'] - h['72o'] < .70 or h['AKs'] - h['32o'] < .55:
            raise ValueError(f'premium vs weak hands inverted: {pos}')
        for high, low in [('AA','22'), ('KK','44'), ('QQ','66'), ('AKs','A2o')]:
            if h[high] + .15 < h[low]:
                raise ValueError(f'{pos}: {high} is played less than {low}')
        for suited, off in [('A5s','A5o'), ('K5s','K5o'), ('Q5s','Q5o'), ('J5s','J5o'), ('T5s','T5o')]:
            if h[suited] + .20 < h[off]:
                raise ValueError(f'{pos}: {suited} anomalously worse than {off}')
    weak = ['32o','42o','52o','62o','72o','82o','92o','T2o','J2o','Q2o']
    btn = {h['hand']: h['open'] for h in data['BTN RFI']['hands']}
    if sum(btn[h] for h in weak) / len(weak) > .35:
        raise ValueError('BTN weak offsuit range is implausibly wide')


def compare(a, b, name):
    result = {}
    for pos in POSITIONS:
        left, right = a[pos], b[pos]
        x, y = ({r['hand']:r for r in side['hands']} for side in (left,right))
        rms = math.sqrt(sum(x[h]['combos'] * (x[h]['open']-y[h]['open'])**2 for h in x)/1326)
        total = abs(left['open']-right['open'])
        result[pos] = {'combo_weighted_rms':rms,'total_open_difference':total}
        if rms > .16 or total > .08:
            raise ValueError(f'{name}: {pos} unstable: RMS={rms:.3f}, total={total:.3f}')
    return result


def check_policy(policy_path, charts):
    policy = json.loads(policy_path.read_text())
    if policy['max_stack_bb'] != 20 or policy['bet_sizes_half_bb'] != [[4,5],[14],[28]] or policy.get('min_allin_depth') != 0 or policy.get('oop_pot_tax') != 0:
        raise ValueError('stack or action abstraction mismatch')
    histories = policy['histories']
    for history, rows in histories.items():
        if len(rows) != 169:
            raise ValueError(f'invalid bucket count: {history}')
        for row in rows:
            if row is not None and (not all(math.isfinite(p) and 0 <= p <= 1 for p in row) or abs(sum(row)-1) > .002):
                raise ValueError(f'invalid exported probability: {history}')
    for pos, prefix in zip(POSITIONS, ['','00','0000','000000','00000000']):
        rows = histories.get(prefix)
        if rows is None or len(rows) != 169:
            raise ValueError(f'missing 169-bucket policy at {pos}')
        for row in rows:
            if row is not None and (not all(0 <= p <= 1 for p in row) or abs(sum(row)-1) > .002):
                raise ValueError(f'invalid policy probability: {pos}')
    # Q5o is bucket 91 + 10*9/2 + 3; compare chart and full-policy exports.
    btn = next(r for r in charts['BTN RFI']['hands'] if r['hand']=='Q5o')
    policy_btn = histories['000000'][139]
    if policy_btn is None or len(policy_btn) != 4 or abs(sum(policy_btn[1:])-btn['open']) > .003:
        raise ValueError('BTN Q5o policy does not match the RFI chart')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('chart', type=Path)
    parser.add_argument('--policy', type=Path)
    parser.add_argument('--seed', type=Path, help='same iterations, different seed')
    parser.add_argument('--half', type=Path, help='same seed, fewer iterations')
    parser.add_argument('--output', type=Path)
    args=parser.parse_args()
    data=report(args.chart)
    check_chart(data)
    summary={'rfi':{pos:{'open':data[pos]['open'],'limp':data[pos]['limp']} for pos in POSITIONS}}
    if args.policy: check_policy(args.policy,data)
    if args.seed: summary['seed_stability']=compare(data,report(args.seed),'seed')
    if args.half: summary['iteration_stability']=compare(data,report(args.half),'iterations')
    if args.output: args.output.write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))


if __name__=='__main__': main()
