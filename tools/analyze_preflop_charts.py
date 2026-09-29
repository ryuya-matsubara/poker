"""Report every 169-hand RFI frequency and combo-weighted totals."""
import argparse
import csv
import json
from pathlib import Path


def report(path):
    spots = json.loads(Path(path).read_text())
    output = {}
    for spot in spots:
        rows = []
        for item in spot['hands']:
            label = item['hand']
            combos = 6 if len(label) == 2 else 4 if label.endswith('s') else 12
            actions = {a['action']: a['prob'] for a in item['actions']}
            if not actions or abs(sum(actions.values()) - 1) > 0.002:
                raise ValueError(f'invalid strategy: {spot["spot_name"]} {label}')
            rows.append({'hand': label, 'combos': combos,
                         'open': sum(p for action, p in actions.items() if action.startswith('raise')),
                         'limp': actions.get('call', 0), 'actions': actions})
        if len(rows) != 169 or sum(r['combos'] for r in rows) != 1326:
            raise ValueError(f'incomplete chart: {spot["spot_name"]}')
        output[spot['spot_name']] = {'open': sum(r['combos'] * r['open'] for r in rows) / 1326,
                                     'limp': sum(r['combos'] * r['limp'] for r in rows) / 1326,
                                     'hands': rows}
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('chart', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    data = report(args.chart)
    for spot, info in data.items():
        h = next(r for r in info['hands'] if r['hand'] == 'Q5o')
        print(f'{spot}: open={info["open"]:.4%}, limp={info["limp"]:.4%}, Q5o={h["open"]:.4%}')
    if args.output:
        args.output.write_text(json.dumps(data, separators=(',', ':')))
        with args.output.with_suffix('.csv').open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['position', 'hand', 'combos', 'open', 'limp'])
            for spot, info in data.items():
                for h in info['hands']:
                    writer.writerow([spot, h['hand'], h['combos'], h['open'], h['limp']])


if __name__ == '__main__':
    main()
