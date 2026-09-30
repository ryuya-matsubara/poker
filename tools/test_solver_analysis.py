"""Diagnostic invariants; tests never train or prescribe action frequencies."""
import json,tempfile,unittest
from pathlib import Path
from analyze_jam import ev_summary,policy_delta
from validate_preflop import check_chart
from analyze_preflop_charts import report

class AnalysisTests(unittest.TestCase):
    def test_ev_gap_is_max_of_conditional_means(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'ev.json'
            p.write_text(json.dumps([{'spot':'BTN RFI','hand':'AQo','actions':[
                {'action':'fold','probability':.1,'mean_bb':0,'se_bb':0},
                {'action':'raise 4','probability':.8,'mean_bb':2,'se_bb':.1,'jam_difference_se_bb':.08},
                {'action':'allin','probability':.1,'mean_bb':1,'se_bb':.1}]}]))
            s=ev_summary(p)[0]
            self.assertAlmostEqual(s['policy_ev_bb'],1.7)
            self.assertAlmostEqual(s['one_step_deviation_gain_bb'],.3)
            self.assertAlmostEqual(s['jam_minus_best_small_bb'],-1)
            self.assertEqual(s['paired_se_bb'],.08)
            self.assertEqual(s['warnings'],[])
    def test_policy_delta_matches_actual_shared_infosets(self):
        with tempfile.TemporaryDirectory() as root:
            a,b=Path(root)/'a.json',Path(root)/'b.json'
            a.write_text(json.dumps({'histories':{'00':[[1,0],None,[.3,.7]]}}))
            b.write_text(json.dumps({'histories':{'00':[[.9,.1],[.5,.5],[.2,.8]],'0000':[]}}))
            d=policy_delta(a,b)
            self.assertEqual(d['infosets'],2)
            self.assertAlmostEqual(d['mean_l1'],.2)
    def test_premium_collapse_is_detected(self):
        data=report('analysis/old_preflop_charts.json') if Path('analysis/old_preflop_charts.json').exists() else report('preflop_charts.json')
        aa=next(r for r in data['BTN RFI']['hands'] if r['hand']=='AA')
        aa['open']=0
        with self.assertRaisesRegex(ValueError,'premium'):
            check_chart(data)

if __name__=='__main__':unittest.main()
