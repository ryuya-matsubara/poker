"""Verify integrity of a user-requested experimental snapshot; preserve failed science gates."""
import json,hashlib
from pathlib import Path
from analyze_preflop_charts import report
from validate_preflop import check_chart,check_policy
def main():
    q=json.loads(Path('analysis/quality.json').read_text())
    if q.get('release_kind')!='experimental-unconverged':raise ValueError('not an experimental snapshot')
    assert q['gto_certified'] is False
    assert q['release_gate']['ready'] is False
    assert q['published_seed']==42 and q['published_iterations']==80000000
    for name,h in q['source_sha256'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h
    for name,h in q['artifact_sha256'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h
    assert Path('preflop_charts.json').read_bytes()==Path('analysis/current_snapshot/seed42-80m/80m-chart.json').read_bytes()
    assert Path('preflop_policy.json').read_bytes()==Path('analysis/current_snapshot/seed42-80m/final-policy.json').read_bytes()
    check_chart(report(Path('preflop_charts.json')));check_policy(Path('preflop_policy.json'),report(Path('preflop_charts.json')))
    assert '実験版（学習途中・未収束）' in Path('index.html').read_text()
    print('Experimental snapshot integrity verified; convergence NOT certified.')
if __name__=='__main__':main()
