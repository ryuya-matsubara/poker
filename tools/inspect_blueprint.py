"""Attach actual cumulative regret to frozen action EV without changing policy."""
import argparse,json
from pathlib import Path
from export_preflop_policy import entries

def main():
    p=argparse.ArgumentParser();p.add_argument('blueprint',type=Path);p.add_argument('ev',type=Path);args=p.parse_args()
    data=json.loads(args.ev.read_text());needed={}
    # Derive the canonical rank/suited index using the upstream 169 encoding.
    ranks='23456789TJQKA'
    def canon(label):
        hi,lo=sorted([ranks.index(label[0]),ranks.index(label[1])],reverse=True)
        return hi if hi==lo else (13 if label.endswith('s') else 91)+hi*(hi-1)//2+lo
    for s in data:needed[('000000' if s['spot']=='BTN RFI' else '010000',canon(s['hand']))]=s
    iterator=entries(args.blueprint,include_regrets=True);next(iterator)
    for history,b,cum,regret in iterator:
        s=needed.get((history,b))
        if s is not None:
            if len(s['actions'])!=len(regret):raise ValueError('action count mismatch')
            positive=sum(max(0,r) for r in regret)
            for a,r in zip(s['actions'],regret):
                a['stored_cumulative_regret_half_bb']=r
                a['current_regret_matching_probability']=max(0,r)/positive if positive else 1/len(regret)
            del needed[(history,b)]
    if needed:raise ValueError('missing measured infoset')
    args.ev.write_text(json.dumps(data,indent=2))

if __name__=='__main__':main()
