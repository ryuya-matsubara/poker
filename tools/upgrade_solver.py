"""Layer reach-corrected diagnostics and bounded raises on the pinned patch."""
from pathlib import Path
from patch_solver_base import patch, replace_once
import argparse

def upgrade(directory):
    patch(directory)
    p=directory/'preflop.rs';s=p.read_text()
    s=s.replace('#[path = "continuation.rs"] mod continuation;','#[path = "continuation.rs"] mod continuation;\n#[path = "continuation_legacy.rs"] mod continuation_legacy;')
    s=replace_once(s,'    postflop: HashMap<continuation::InfoKey, RegretEntry>,','    postflop: HashMap<continuation::InfoKey, RegretEntry>,\n    shared_runout: [Card;5],\n    post_strategy: HashMap<continuation::InfoKey,Vec<f32>>,\n    pre_strategy: HashMap<PreflopInfoKey,Vec<f32>>,')
    s=replace_once(s,'            postflop: HashMap::new(),','            postflop: HashMap::new(),\n            shared_runout: [0;5],\n            post_strategy: HashMap::new(),\n            pre_strategy: HashMap::new(),')
    s=s.replace('            self.cfr_external(&state, traverser, &mut history);','''            self.post_strategy.clear();self.pre_strategy.clear();
            let samples=if std::env::var("POKER_MODEL").ok().as_deref()==Some("chance") {2}else{1};
            // Fork decision RNG from chance RNG. CRN branch cloning must never
            // rewind the stream that generates the NEXT deal or board.
            let continuation_seed=self.rng.gen::<u64>();
            let next_deal_rng=self.rng.clone();
            self.rng=SmallRng::seed_from_u64(continuation_seed);
            for _ in 0..samples {
                let mut dead=state.holes.iter().fold(Hand::new(),|d,&h|d.union(h));
                for i in 0..5 {let c=self.draw_excluding(dead);self.shared_runout[i]=c;dead=dead.add(c);}
                let decision_seed=self.rng.gen::<u64>();
                let next_board_rng=self.rng.clone();
                self.rng=SmallRng::seed_from_u64(decision_seed);
                match std::env::var("POKER_MODEL").unwrap_or_else(|_|"full".into()).as_str() {
                    "legacy"|"nojam"|"raw" => {self.cfr_external(&state,traverser,&mut history);},
                    _ => {continuation::train(self,&state,traverser,&mut history);}
                }
                self.rng=next_board_rng;
            }
            self.rng=next_deal_rng;''',1)
    # Separate action reopening permission from whether a player owes a call.
    s=s.replace('    pub last_aggressor: Option<u8>,','    pub last_aggressor: Option<u8>,\n    pub raise_allowed: [bool;6],')
    s=s.replace('            last_aggressor: None,','            last_aggressor: None,\n            raise_allowed: [true;6],')
    s=s.replace('        match action {','        s.raise_allowed[p]=false;\n        match action {',1)
    s=s.replace('s.has_acted[i] = false;','s.has_acted[i] = false;\n                        s.raise_allowed[i]=true;',2)
    s=s.replace('if !actions.contains(&PreflopAction::Raise(total_bet))','if self.raise_allowed[p] && !actions.contains(&PreflopAction::Raise(total_bet))')
    s=s.replace('if my_stack > to_call && self.n_raises','if self.raise_allowed[p] && my_stack > to_call && self.n_raises')
    s=s.replace('if my_stack > 0 && self.n_raises','if self.raise_allowed[p] && my_stack > 0 && self.n_raises')
    s=s.replace('if chips_needed <= 0 {','if chips_needed <= 0 || total_bet-max_bet < self.last_raise_size {')
    s+='''
#[cfg(test)]
mod reopening_regression {
 use super::*;
 #[test] fn short_allin_does_not_reopen_for_prior_actor() {
  let cfg=PreflopBetConfig{raise_sizes:vec![vec![4,5],vec![14],vec![28]],sb_limp:true,sb_open_size:Some(6),min_allin_depth:0};
  let mut s=PreflopState::new_6max(cfg);s=s.apply(PreflopAction::Raise(4));
  s.stacks[1]=5;s=s.apply(PreflopAction::AllIn);
  for _ in 0..4 {s=s.apply(PreflopAction::Fold);}
  assert_eq!(s.to_act,0);assert_eq!(s.actions(),vec![PreflopAction::Fold,PreflopAction::Call]);
 }
}
#[cfg(test)]
mod chance_stream_regression {
 use super::*;
 #[test] fn next_deal_rng_is_independent_of_action_tree() {
  let cfg=PreflopBetConfig{raise_sizes:vec![vec![4,5],vec![14],vec![28]],sb_limp:true,sb_open_size:Some(6),min_allin_depth:0};
  let mut other=cfg.clone();other.raise_sizes=vec![vec![4,5],vec![10,14],vec![]];
  let mut a=PreflopTrainer::new(cfg,2026);let mut b=PreflopTrainer::new(other,2026);
  a.train(100);b.train(100);
  assert_eq!(a.rng.gen::<u64>(),b.rng.gen::<u64>());
 }
}
impl PreflopTrainer {
    pub fn diagnose_actions(&mut self,path:&str,samples:usize) {continuation::diagnose(self,path,samples);}
}
'''
    s=s.replace('postflop: HashMap<continuation::InfoKey, RegretEntry>', 'postflop: HashMap<continuation::InfoKey, continuation::PostEntry>')
    p.write_text(s)
    legacy=Path(__file__).with_name('continuation_legacy.rs').read_text()
    legacy=legacy.replace('use super::{PreflopState, PreflopTrainer, RegretEntry, NUM_PLAYERS};','use super::{PreflopState, PreflopTrainer, NUM_PLAYERS};\nuse super::continuation::PostEntry as RegretEntry;')
    legacy=legacy.replace('#[derive(Clone, Copy, Hash, Eq, PartialEq)]\npub(super) struct InfoKey(pub u64);','pub(super) type InfoKey = super::continuation::InfoKey;')
    legacy=legacy.replace('InfoKey(value)','super::continuation::InfoKey(value as u128)')
    legacy=legacy.replace('fn features(','pub(super) fn visible_features(').replace('features(', 'visible_features(').replace('visible_visible_features','visible_features')
    legacy=legacy.replace('fn cfr(trainer: &mut PreflopTrainer,node: &Node,t: u8)', 'fn cfr(trainer: &mut PreflopTrainer,node: &Node,t: u8,learn: bool)')
    legacy=legacy.replace('cfr(trainer,&next,t)','cfr(trainer,&next,t,learn)').replace('cfr(trainer,&apply(a),t)','cfr(trainer,&apply(a),t,learn)')
    legacy=legacy.replace('if p==t as usize {','if p==t as usize && learn {')
    legacy=legacy.replace('.current_strategy();','.current_strategy();')
    old='let strategy=trainer.postflop.entry(k).or_insert_with(||RegretEntry::new(actions.len())).current_strategy();'
    new='let strategy=trainer.postflop.entry(k).or_insert_with(||RegretEntry::new(actions.len()));let strategy=if learn {strategy.current_strategy()}else{strategy.average_strategy()};'
    assert old in legacy;legacy=legacy.replace(old,new)
    legacy=legacy.replace('cfr(trainer,&node,t)','cfr(trainer,&node,t,true)')
    start=legacy.index('    let mut dead=state.holes.iter()');end=legacy.index('    let board=runout[..3]',start)
    legacy=legacy[:start]+'    let runout=trainer.shared_runout;\n'+legacy[end:]
    block=legacy[legacy.index('pub(super) fn terminal_value'):legacy.index('#[cfg(test)]')]
    block=block.replace('fn terminal_value','fn evaluate_policy').replace('cfr(trainer,&node,t,true)','cfr(trainer,&node,t,false)')
    legacy=legacy.replace('#[cfg(test)]',block+'\n#[cfg(test)]',1)
    (directory/'continuation_legacy.rs').write_text(legacy)
    m=directory/'main.rs';v=m.read_text()
    v=v.replace('    trainer.train(iterations);','''    if std::env::var("POKER_MODEL").ok().as_deref()==Some("nojam") {trainer.blueprint.config.min_allin_depth=1;}
    if std::env::var("POKER_MODEL").ok().as_deref()==Some("sizes") {trainer.blueprint.config.raise_sizes=vec![vec![4,5],vec![10,14],vec![]];}
    if let Ok(prefix)=std::env::var("POKER_CHECKPOINT_PREFIX") {
        for end in [30000000u64,60000000,120000000].into_iter().filter(|&x|x<=iterations) {
            trainer.train(end-trainer.blueprint.iterations);
            let stem=format!("{}/{}m",prefix,end/1000000);
            std::fs::write(format!("{}-chart.json",stem),serde_json::to_string_pretty(&trainer.blueprint.extract_charts()).unwrap()).unwrap();
            let mut f=std::fs::File::create(format!("{}-blueprint.bin",stem)).unwrap();trainer.blueprint.save(&mut f).unwrap();
            trainer.diagnose_actions(&format!("{}-ev.json",stem),10000);
        }
        if trainer.blueprint.iterations<iterations {trainer.train(iterations-trainer.blueprint.iterations);}
    } else {trainer.train(iterations);}
    if let Ok(path)=std::env::var("POKER_EV_OUTPUT") {
        let samples=std::env::var("POKER_EV_SAMPLES").ok().and_then(|n|n.parse().ok()).unwrap_or(10000);
        trainer.diagnose_actions(&path,samples);
    }''',1)
    m.write_text(v)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source_dir',type=Path);upgrade(p.parse_args().source_dir)
