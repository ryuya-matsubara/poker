"""Print the requested RFI hand frequencies from a chart or analysis JSON."""
import argparse
from pathlib import Path

from analyze_preflop_charts import report

BTN = '32o 54o 65o 76o T5o J2o J5o Q2o Q5o Q8o K2o A2o 22 A5s Q5s'.split()
UTG = '22 55 77 99 JTs QJs KJs A5s A9s AJo AQo AKs AKo'.split()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('chart', type=Path)
    args = parser.parse_args()
    spots = report(args.chart)
    for position, names in [('BTN RFI', BTN), ('UTG RFI', UTG)]:
        rows = {row['hand']: row for row in spots[position]['hands']}
        print(f'## {position}')
        print('| Hand | Raise / shove | Limp | Fold |')
        print('| --- | ---: | ---: | ---: |')
        for name in names:
            row = rows[name]
            play = row['open'] + row['limp']
            print(f'| {name} | {row["open"]:.1%} | {row["limp"]:.1%} | {1-play:.1%} |')


if __name__ == '__main__':
    main()
