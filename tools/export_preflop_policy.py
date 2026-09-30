"""Export frequently sampled preflop infosets from DCFR-SOLVER's binary blueprint.

Upstream format: exinori/DCFR-SOLVER src/preflop.rs, commit 4ade6a9e.
The output is an approximate average strategy in a restricted 6-player game.
"""
import argparse
import json
import struct
import math
import hashlib
from collections import defaultdict
from pathlib import Path


def read_exact(source, count):
    chunk = source.read(count)
    if len(chunk) != count:
        raise ValueError('Truncated blueprint')
    return chunk


def read_int(source, fmt):
    return struct.unpack('<' + fmt, read_exact(source, struct.calcsize('<' + fmt)))[0]


def entries(path, include_regrets=False):
    with path.open('rb') as source:
        sizes = []
        for _ in range(read_int(source, 'B')):
            sizes.append([read_int(source, 'i') for _ in range(read_int(source, 'B'))])
        sb_limp = bool(read_int(source, 'B'))
        sb_open = read_int(source, 'i')
        min_allin_depth = read_int(source, 'B')
        iterations, count = read_int(source, 'Q'), read_int(source, 'Q')
        config = (sizes, sb_limp, sb_open, min_allin_depth, iterations, count)
        yield config
        for _ in range(count):
            bucket = read_int(source, 'B')
            length = read_int(source, 'H')
            history = read_exact(source, length).hex()
            n = read_int(source, 'H')
            if n < 2 or n > 5 or bucket >= 169:
                raise ValueError('Unexpected action or hand count')
            regrets = struct.unpack('<' + 'f' * n, read_exact(source, 4 * n))
            averages = struct.unpack('<' + 'f' * n, read_exact(source, 4 * n))
            yield (history, bucket, averages, regrets) if include_regrets else (history, bucket, averages)
        if source.read(1):
            raise ValueError('Unexpected bytes after blueprint')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('blueprint', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--max-histories', type=int, default=300)
    parser.add_argument('--min-visits', type=int, default=30, help='Legacy threshold for deep histories only; weighted mass is not a visit count')
    args = parser.parse_args()

    first = entries(args.blueprint)
    config = next(first)
    sizes, sb_limp, sb_open, min_allin, iterations, count = config
    if sizes != [[4,5], [14], [28]] or not sb_limp or sb_open != 6 or min_allin != 0:
        raise ValueError('Blueprint does not match 20BB app action sizes')
    history_mass = defaultdict(float)
    scale = max(1, iterations / 2)
    for history, _, cum in first:
        if not all(math.isfinite(x) and x >= 0 for x in cum):
            raise ValueError('Non-finite or negative cumulative strategy')
        history_mass[history] += sum(cum) / scale
    selected = set(sorted(history_mass, key=history_mass.get, reverse=True)[:args.max_histories])
    # Importance-weighted average mass is not visitation frequency. Retain every
    # sampled shallow decision, including responses to opens; rank only deeper
    # histories to bound browser payload size. No hand-specific selection.
    shallow = {h for h in history_mass if len(h) <= 8}
    selected.update(shallow)

    second = entries(args.blueprint)
    if next(second) != config:
        raise ValueError('Blueprint changed between passes')
    output = {h: [None] * 169 for h in selected}
    kept = 0
    for history, bucket, cum in second:
        if history not in output:
            continue
        total = sum(cum)
        if not all(math.isfinite(x) and x >= 0 for x in cum):
            raise ValueError('Non-finite or negative cumulative strategy')
        if total <= 0 or (history not in shallow and total / scale < args.min_visits):
            continue
        output[history][bucket] = [round(x / total, 4) for x in cum]
        kept += 1
    output = {history: hands for history, hands in output.items() if any(hands)}
    result = {'version': 3, 'iterations': iterations, 'source_commit': '4ade6a9e15a841c41867afde1258b9d110cd6fb1',
              'max_stack_bb': 20, 'bet_sizes_half_bb': sizes, 'sb_open_half_bb': sb_open,
              'min_allin_depth': min_allin, 'continuation_model': 'joint-three-street-cfr-v7',
              'oop_pot_tax': 0, 'rng_scheme': 'isolated-deal-board-decision-streams', 'export_shallow_depth': 4, 'deep_history_mass_threshold': args.min_visits,
              'model_sha256': hashlib.sha256(Path(__file__).with_name('continuation.rs').read_bytes()).hexdigest(),
              'algorithm': 'signed-external-sampling-MCCFR', 'average_weighting': 'linear-own-reach-divided-by-opponent-sample-reach', 'sampling_exploration': 0.05, 'postflop_raise_limit': 1, 'ante_bb': 0, 'rake': 0, 'histories': output}
    args.output.write_text(json.dumps(result, separators=(',', ':'), ensure_ascii=False))
    print(f'{kept} hands in {len(output)} action histories, {count} raw infosets; output {args.output.stat().st_size} bytes')


if __name__ == '__main__':
    main()
