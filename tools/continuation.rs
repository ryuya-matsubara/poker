//! Bounded NLHE continuation. Signed external-sampling regrets and
//! importance-corrected, own-reach-weighted averaging; no payoff bonuses.
use super::{PreflopState,PreflopTrainer,PreflopInfoKey,RegretEntry};
use crate::card::{rank,suit,Card,Hand};
use crate::iso::canonical_hand;
use rand::Rng;
use std::hash::{Hash,Hasher};
use std::collections::hash_map::DefaultHasher;
const ORDER:[usize;6]=[4,5,0,1,2,3];
#[derive(Clone,Copy,Hash,Eq,PartialEq)]
pub(super) struct InfoKey(pub u128);
pub(super) struct PostEntry {pub regrets:[f32;4],pub cum_strategy:[f32;4],n:usize}
impl PostEntry {
 pub(super) fn new(n:usize)->Self {assert!(n<=4);Self{regrets:[0.;4],cum_strategy:[0.;4],n}}
 pub(super) fn current_strategy(&self)->Vec<f32> {let total:f32=self.regrets[..self.n].iter().map(|x|x.max(0.)).sum();if total>0. {self.regrets[..self.n].iter().map(|x|x.max(0.)/total).collect()}else{vec![1./self.n as f32;self.n]}}
 pub(super) fn average_strategy(&self)->Vec<f32> {let total:f32=self.cum_strategy[..self.n].iter().sum();if total>0. {self.cum_strategy[..self.n].iter().map(|x|x/total).collect()}else{vec![1./self.n as f32;self.n]}}
}
trait Entry {fn add(&mut self,a:usize,regret:f32,average:f32);}
impl Entry for RegretEntry {fn add(&mut self,a:usize,r:f32,s:f32){self.regrets[a]+=r;self.cum_strategy[a]+=s;}}
impl Entry for PostEntry {fn add(&mut self,a:usize,r:f32,s:f32){self.regrets[a]+=r;self.cum_strategy[a]+=s;}}
#[derive(Clone)]
struct Node {state:PreflopState,board:Hand,runout:[Card;5],street:usize,paid:[i32;6],pending:u8,acted:u8,bettor:Option<usize>,target:i32,last_raise:i32,raises:u8,history:u64,prehistory:u64,previous:u16}
#[derive(Clone,Copy)]
struct Reach {own:f64,q:f64,cf:f64}
impl Reach {fn root()->Self {Self{own:1.,q:1.,cf:1.}}}
fn mode()->&'static str {static MODE:std::sync::OnceLock<String>=std::sync::OnceLock::new();MODE.get_or_init(||std::env::var("POKER_MODEL").unwrap_or_else(|_|"full".into())).as_str()}
fn rich()->bool {matches!(mode(),"rich"|"full"|"chance"|"sizes")}
fn raises()->bool {matches!(mode(),"raises"|"full"|"chance"|"sizes")}
fn actionable(s:&PreflopState)->u8 {(0..6).filter(|&p|!s.folded[p]&&!s.all_in[p]).fold(0,|m,p|m|1<<p)}
fn wager(s:&mut PreflopState,p:usize,n:i32)->i32 {let n=n.max(0).min(s.stacks[p]);s.stacks[p]-=n;s.bets[p]+=n;s.all_in[p]=s.stacks[p]==0;n}
fn actor(n:&Node)->usize {let start=n.bettor.map(|p|(ORDER.iter().position(|&q|q==p).unwrap()+1)%6).unwrap_or(0);(0..6).map(|i|ORDER[(start+i)%6]).find(|&p|n.pending&(1<<p)!=0).unwrap()}
fn actions(n:&Node,p:usize)->Vec<i32> {
 let stack=n.state.stacks[p];let cap=n.paid[p]+stack;let call=(n.target-n.paid[p]).max(0);
 if call>0 {
  let mut a=vec![-1,n.target.min(cap)];
  if raises()&&n.raises<1&&n.acted&(1<<p)==0&&stack>call {
   let r=(n.target*3).max(n.target+n.last_raise).min(cap);
   if r<cap {a.push(r);} if cap>n.target {a.push(cap);}
  } a
 } else {
  let pot:i32=n.state.bets.iter().sum();let mut a=vec![n.paid[p]];
  for x in [(pot+1)/3,(pot*3+2)/4,stack] {let v=n.paid[p]+x.max(2).min(stack);if !a.contains(&v){a.push(v);}}a
 }
}
fn apply(n:&Node,p:usize,a:i32,index:usize)->Node {
 let mut c=n.clone();c.pending&=!(1<<p);c.acted|=1<<p;c.history=c.history.wrapping_mul(37).wrapping_add((p*5+index+1) as u64);
 if a<0 {c.state.folded[p]=true;return c;}
 let add=(a-c.paid[p]).max(0);let paid=wager(&mut c.state,p,add);c.paid[p]+=paid;
 if c.paid[p]>n.target {
  let increment=c.paid[p]-n.target;let full=n.target==0||increment>=n.last_raise;
  c.bettor=Some(p);c.target=c.paid[p];if n.target>0 {c.raises+=1;}
  if full {c.last_raise=increment.max(2);c.acted=1<<p;}
  c.pending=actionable(&c.state)&!(1<<p);
 }c
}
fn hash<T:Hash>(x:&T)->u64 {let mut h=DefaultHasher::new();x.hash(&mut h);h.finish()}
fn key(n:&Node,p:usize,a:&[i32])->InfoKey {
 let legacy=super::continuation_legacy::visible_features(n.state.holes[p],n.board,n.street);
 if !rich() {return InfoKey(hash(&(legacy,p,n.street,actionable(&n.state),n.target,n.raises,n.history,n.state.n_raises,a)) as u128);}
 let hole:Vec<_>=n.state.holes[p].iter().collect();let hi=hole.iter().map(|&c|rank(c)).max().unwrap();let lo=hole.iter().map(|&c|rank(c)).min().unwrap();
 let mut br=Vec::new();let mut suits=[0u8;4];let mut mask=0u16;for c in n.board.iter(){br.push(rank(c));suits[suit(c) as usize]+=1;mask|=1<<rank(c);}br.sort();
 let over=hole.iter().filter(|&&c|rank(c)>*br.last().unwrap()).count() as u8;
 let own_suits:Vec<u8>=hole.iter().map(|&c|suit(c)).collect();let mut full_suits=suits;for &s in &own_suits{full_suits[s as usize]+=1;}
 let flush=own_suits.iter().map(|&s|full_suits[s as usize]).max().unwrap();
 let nut=hole.iter().any(|&c|rank(c)==12&&suits[suit(c) as usize]>=2);
 let near=hole.iter().any(|&c|rank(c)==11&&suits[suit(c) as usize]>=2);
 for &c in &hole {mask|=1<<rank(c);}let wheel=(mask<<1)|((mask>>12)&1);
 let straight=(0..=9).map(|i|((wheel>>i)&31).count_ones()).max().unwrap() as u8;
 let pot:i32=n.state.bets.iter().sum();let call=(n.target-n.paid[p]).max(0);
 let effective=(0..6).filter(|&i|i!=p&&!n.state.folded[i]).map(|i|n.state.stacks[i]+n.paid[i]).max().unwrap_or(0).min(n.state.stacks[p]+n.paid[p]);
 // Private identity is 169 rank/suited classes, not 1326 suit-labelled combos.
 // Public board ranks and suit topology are bucketed; exact money/history are retained.
 let private=(canonical_hand(hole[0],hole[1]).index(),legacy,over,hi,lo,flush,straight,nut,near);
 let public=(br.last().unwrap()/3,br[br.len()/2]/3,br[0]/3,suits.iter().max().copied().unwrap(),br.windows(2).any(|w|w[0]==w[1]));
 let odds=(16*call/(pot+call).max(1)).min(15);
 let bet_fraction=(8*n.target/(pot-n.paid.iter().sum::<i32>()).max(1)).min(31);
 let stacks=n.state.stacks.map(|x|(x+1)/4); // 2BB resolution; payoffs use exact chips.
 let money=((pot+2)/4,stacks,(effective+1)/4,odds,bet_fraction,a.len());
 InfoKey((hash(&(private,public)) as u128)<<64|hash(&(p,n.street,actionable(&n.state),n.state.folded,n.state.last_aggressor,n.prehistory,n.history,n.previous,money)) as u128)
}
fn terminal(n:&Node,t:u8)->f32 {if n.state.active_count()==1 {let w=(0..6).find(|&p|!n.state.folded[p]).unwrap();n.state.payoff_fold(w as u8)[t as usize]}else{n.state.payoff_showdown(n.runout.iter().fold(Hand::new(),|h,&c|h.add(c)))[t as usize]}}
fn update<E:Entry>(e:&mut E,s:&[f32],v:&[f32],value:f32,r:Reach,weight:f64) {
 for a in 0..s.len(){e.add(a,(r.cf*(v[a]-value) as f64) as f32,(weight*r.own/r.q*s[a] as f64) as f32);}
}
fn cfr(t:&mut PreflopTrainer,n:&Node,tr:u8,r:Reach,learn:bool)->f32 {
 if n.state.folded[tr as usize]{return -(n.state.bets[tr as usize] as f32);}
 if n.state.active_count()==1{return terminal(n,tr);}
 if n.pending==0 || actionable(&n.state).count_ones()<2&&n.target==0 {
  if n.street==5||actionable(&n.state).count_ones()<2{return terminal(n,tr);}
  let mut c=n.clone();c.street+=1;c.board=c.board.add(c.runout[c.street-1]);c.paid=[0;6];c.target=0;c.last_raise=2;c.raises=0;c.acted=0;c.previous=((n.previous<<5)|((n.bettor.unwrap_or(6) as u16)<<2)|n.raises.min(3) as u16)&1023;c.history=0;c.bettor=None;c.pending=actionable(&c.state);return cfr(t,&c,tr,r,learn);
 }
 let p=actor(n);let a=actions(n,p);let k=key(n,p,&a);
 let s=if learn {
  if !t.post_strategy.contains_key(&k) {let v=t.postflop.get(&k).map(|e|e.current_strategy()).unwrap_or_else(||vec![1./a.len() as f32;a.len()]);t.post_strategy.insert(k,v);}
  t.post_strategy[&k].clone()
 }else{t.postflop.get(&k).map(|e|e.average_strategy()).unwrap_or_else(||vec![1./a.len() as f32;a.len()])};
 if p==tr as usize&&learn {
  let shared=t.rng.clone();let mut v=Vec::new();for (i,&x) in a.iter().enumerate(){t.rng=shared.clone();v.push(cfr(t,&apply(n,p,x,i),tr,Reach{own:r.own*s[i] as f64,..r},true));}
  let value=v.iter().zip(&s).map(|(x,p)|x*p).sum();let w=t.blueprint.iterations as f64+1.;let e=t.postflop.entry(k).or_insert_with(||PostEntry::new(a.len()));update(e,&s,&v,value,r,w);value
 } else {
  let epsilon=if learn{0.05}else{0.};let q:Vec<_>=s.iter().map(|&x|(1.-epsilon)*x+epsilon/a.len() as f32).collect();let i=sample(&q,&mut t.rng);
  let ratio=s[i] as f64/q[i] as f64;let next=if learn{Reach{q:r.q*q[i] as f64,cf:r.cf*ratio,..r}}else{r};cfr(t,&apply(n,p,a[i],i),tr,next,learn)*ratio as f32
 }
}
fn sample<R:Rng>(s:&[f32],rng:&mut R)->usize {let u=rng.gen::<f32>();let mut c=0.;s.iter().position(|&p|{c+=p;u<c}).unwrap_or(s.len()-1)}
fn public_preflop(s:&PreflopState,h:&[u8])->u64 {
 let mut replay=PreflopState::new_6max(s.config.clone());let mut raises=Vec::new();
 for &idx in h {let a=replay.actions();if idx as usize>=a.len(){break;}let x=a[idx as usize];if matches!(x,super::PreflopAction::Raise(_)|super::PreflopAction::AllIn){raises.push((replay.to_act,x));}replay=replay.apply(x);}
 hash(&raises)
}
fn node(s:&PreflopState,runout:[Card;5],history:&[u8])->Node {Node{state:s.clone(),board:runout[..3].iter().fold(Hand::new(),|h,&c|h.add(c)),runout,street:3,paid:[0;6],pending:actionable(s),acted:0,bettor:None,target:0,last_raise:2,raises:0,history:0,prehistory:public_preflop(s,history),previous:0}}
fn leaf(t:&mut PreflopTrainer,s:&PreflopState,tr:u8,h:&[u8],r:Reach,learn:bool)->f32 {
 if mode()=="raw"{return s.payoff_showdown(t.shared_runout.iter().fold(Hand::new(),|b,&c|b.add(c)))[tr as usize];}
 if mode()=="legacy"||mode()=="nojam" {return super::continuation_legacy::evaluate_policy(t,s,tr);}
 cfr(t,&node(s,t.shared_runout,h),tr,r,learn)
}
fn pre(t:&mut PreflopTrainer,s:&PreflopState,tr:u8,h:&mut Vec<u8>,r:Reach,learn:bool)->f32 {
 match s.node_type(){super::PreflopNodeType::TerminalFold(w)=>s.payoff_fold(w)[tr as usize],super::PreflopNodeType::TerminalShowdown=>leaf(t,s,tr,h,r,learn),super::PreflopNodeType::Decision(p)=>{
 let a=s.actions();let cards:Vec<_>=s.holes[p as usize].iter().collect();let k=PreflopInfoKey{bucket:canonical_hand(cards[0],cards[1]).index(),history:h.clone()};let strat=if learn {
 if !t.pre_strategy.contains_key(&k){let v=t.blueprint.entries.get(&k).map(|e|e.current_strategy()).unwrap_or_else(||vec![1./a.len() as f32;a.len()]);t.pre_strategy.insert(k.clone(),v);}
 t.pre_strategy[&k].clone()
 }else{t.blueprint.entries.get(&k).map(|e|e.average_strategy()).unwrap_or_else(||vec![1./a.len() as f32;a.len()])};
 if p==tr&&learn {let shared=t.rng.clone();let mut values=vec![0.;a.len()];for (i,&x) in a.iter().enumerate(){t.rng=shared.clone();h.push(i as u8);values[i]=pre(t,&s.apply(x),tr,h,Reach{own:r.own*strat[i] as f64,..r},true);h.pop();}let value=values.iter().zip(&strat).map(|(v,p)|v*p).sum();let w=t.blueprint.iterations as f64+1.;update(t.blueprint.entries.entry(k).or_insert_with(||RegretEntry::new(a.len())),&strat,&values,value,r,w);value}
 else {let epsilon=if learn{0.05}else{0.};let q:Vec<_>=strat.iter().map(|&x|(1.-epsilon)*x+epsilon/a.len() as f32).collect();let i=sample(&q,&mut t.rng);h.push(i as u8);let ratio=strat[i] as f64/q[i] as f64;let v=pre(t,&s.apply(a[i]),tr,h,if learn{Reach{q:r.q*q[i] as f64,cf:r.cf*ratio,..r}}else{r},learn);h.pop();v*ratio as f32}
 } }
}
pub(super) fn train(t:&mut PreflopTrainer,s:&PreflopState,tr:u8,h:&mut Vec<u8>)->f32 {pre(t,s,tr,h,Reach::root(),true)}
// Frozen policy evaluation. Deals are conditioned on ALL earlier public actions,
// not a uniform UTG range. Each action reuses the deal, board and RNG seed.
pub(super) fn diagnose(t:&mut PreflopTrainer,path:&str,samples:usize) {
 use rand::SeedableRng;use rand::rngs::SmallRng;use serde_json::json;
 let saved_rng=t.rng.clone();let saved_board=t.shared_runout;let mut out=Vec::new();
 for (spot,label) in [("BTN RFI","AQo"),("BTN RFI","AA"),("BTN RFI","A5s"),("BTN RFI","22"),("BTN RFI","Q5o"),("UTG 2BB -> BTN","53s"),("UTG 2BB -> BTN","AQo")] {
  let mut rng=SmallRng::seed_from_u64(9127);let bucket=(0..169u8).find(|&i|crate::iso::CanonicalHand::from_index(i).to_string()==label).unwrap();let mut sums=Vec::<f64>::new();let mut squares=Vec::<f64>::new();let mut names=Vec::new();let mut probabilities=Vec::new();let mut regret_sums=Vec::<f64>::new();let mut regret_squares=Vec::<f64>::new();let mut paired_sums=Vec::<f64>::new();let mut paired_squares=Vec::<f64>::new();let mut accepted=0;let mut attempts=0;
  while accepted<samples&&attempts<samples*20000 {attempts+=1;t.rng=rng.clone();let holes=t.deal_holes();rng=t.rng.clone();let hc:Vec<_>=holes[3].iter().collect();if canonical_hand(hc[0],hc[1]).index()!=bucket{continue;}
   let mut s=PreflopState::new_6max(t.blueprint.config.clone());s.holes=holes;let prefix=if spot=="BTN RFI"{vec![0,0,0]}else{vec![1,0,0]};let mut h=Vec::new();let mut ok=true;
   for &idx in &prefix {let p=s.to_act;let cs:Vec<_>=s.holes[p as usize].iter().collect();let k=PreflopInfoKey{bucket:canonical_hand(cs[0],cs[1]).index(),history:h.clone()};let a=s.actions();let st=t.blueprint.entries.get(&k).map(|e|e.average_strategy()).unwrap_or_else(||vec![1./a.len() as f32;a.len()]);if rng.gen::<f32>()>st[idx]{ok=false;break;}s=s.apply(a[idx]);h.push(idx as u8);}if !ok{continue;}
   let mut dead=holes.iter().fold(Hand::new(),|d,&x|d.union(x));for i in 0..5 {loop{let c=rng.gen_range(0..52);if !dead.contains(c){t.shared_runout[i]=c;dead=dead.add(c);break;}}}
   let a=s.actions();if sums.is_empty(){sums=vec![0.;a.len()];squares=sums.clone();regret_sums=sums.clone();regret_squares=sums.clone();paired_sums=sums.clone();paired_squares=sums.clone();names=a.iter().map(|x|x.to_string()).collect();let k=PreflopInfoKey{bucket,history:h.clone()};probabilities=t.blueprint.entries.get(&k).map(|e|e.average_strategy()).unwrap_or_else(||vec![1./a.len() as f32;a.len()]);}
   let common=rng.clone();let mut vv=Vec::new();for(i,&x)in a.iter().enumerate(){t.rng=common.clone();h.push(i as u8);let v=pre(t,&s.apply(x),3,&mut h,Reach::root(),false) as f64/2.;h.pop();sums[i]+=v;squares[i]+=v*v;vv.push(v);}let value:f64=vv.iter().zip(&probabilities).map(|(v,p)|v*(*p as f64)).sum();let jam_index=a.iter().position(|x|matches!(x,super::PreflopAction::AllIn));for i in 0..vv.len(){let regret=vv[i]-value;regret_sums[i]+=regret;regret_squares[i]+=regret*regret;if let Some(j)=jam_index{let gap=vv[j]-vv[i];paired_sums[i]+=gap;paired_squares[i]+=gap*gap;}}accepted+=1;
  }
  assert!(accepted==samples,"Insufficient conditional action EV samples: {} {} {}/{}",spot,label,accepted,samples);let n=accepted as f64;let se=|sum:f64,sq:f64|((sq-sum*sum/n)/(n-1.)/n).max(0.).sqrt();let rows:Vec<_>=(0..sums.len()).map(|i|{let mean=sums[i]/n;let err=se(sums[i],squares[i]);json!({"action":names[i],"probability":probabilities[i],"mean_bb":mean,"se_bb":err,"ci95_bb":[mean-1.96*err,mean+1.96*err],"samples":accepted,"estimated_regret_bb":regret_sums[i]/n,"regret_se_bb":se(regret_sums[i],regret_squares[i]),"jam_minus_action_bb":paired_sums[i]/n,"jam_difference_se_bb":se(paired_sums[i],paired_squares[i])})}).collect();out.push(json!({"spot":spot,"hand":label,"actions":rows,"attempts":attempts}));
 }
 std::fs::write(path,serde_json::to_string_pretty(&out).unwrap()).unwrap();t.rng=saved_rng;t.shared_runout=saved_board;
}

pub(super) fn terminal_value(t:&mut PreflopTrainer,s:&PreflopState,tr:u8)->f32 {if mode()=="raw" {s.payoff_showdown(t.shared_runout.iter().fold(Hand::new(),|h,&c|h.add(c)))[tr as usize]}else{super::continuation_legacy::terminal_value(t,s,tr)}}

#[cfg(test)]
mod tests {
 use super::*;use crate::card::card;use super::super::PreflopBetConfig;
 #[test] fn signed_regrets_and_average_reach() {
  let mut e=RegretEntry::new(2);update(&mut e,&[0.5,0.5],&[-2.,2.],0.,Reach{own:0.2,q:0.5,cf:0.25},10.);
  assert_eq!(e.regrets,vec![-0.5,0.5]);assert_eq!(e.cum_strategy,vec![2.,2.]);assert_eq!(e.current_strategy(),vec![0.,1.]);
 }
 #[test] fn importance_sampling_preserves_expectation() {
  let pi=[0.8,0.2];let q=[0.6,0.4];let u=[-4.,6.];let expected:f64=(0..2).map(|i|q[i]*(pi[i]/q[i])*u[i]).sum();assert!((expected+2.).abs()<1e-9);
 }
 #[test] fn richer_private_identity_separates_merged_high_cards() {
  let mut s=PreflopState::new_6max(PreflopBetConfig::default());s.holes[0]=Hand::new().add(card(11,0)).add(card(10,1));
  let mut n=node(&s,[card(7,0),card(4,1),card(0,2),card(1,3),card(2,0)],&[1,0,0]);let weak=Hand::new().add(card(5,2)).add(card(1,1));
  assert_eq!(super::super::continuation_legacy::visible_features(s.holes[0],n.board,3).0,super::super::continuation_legacy::visible_features(weak,n.board,3).0);
  if rich(){let a=actions(&n,0);let k=key(&n,0,&a);n.state.holes[0]=weak;assert!(key(&n,0,&a)!=k);}
 }
 #[test] fn randomized_terminal_conservation() {
  let mut t=PreflopTrainer::new(PreflopBetConfig{raise_sizes:vec![vec![4,5],vec![14],vec![28]],sb_limp:true,sb_open_size:Some(6),min_allin_depth:0},81);
  for _ in 0..10000 {
   let mut s=PreflopState::new_6max(t.blueprint.config.clone());s.holes=t.deal_holes();let mut dead=s.holes.iter().fold(Hand::new(),|h,&x|h.union(x));let mut runout=[0;5];for c in &mut runout{*c=t.draw_excluding(dead);dead=dead.add(*c);}
   for _ in 0..80 {match s.node_type(){super::super::PreflopNodeType::Decision(_)=>{let a=s.actions();s=s.apply(a[t.rng.gen_range(0..a.len())]);},_=>break}}
   let v=if let super::super::PreflopNodeType::TerminalFold(w)=s.node_type(){s.payoff_fold(w)}else{s.payoff_showdown(runout.iter().fold(Hand::new(),|h,&c|h.add(c)))};
   assert!(v.iter().sum::<f32>().abs()<0.0001);assert!(s.stacks.iter().all(|&x|x>=0));assert!((0..6).all(|p|s.stacks[p]+s.bets[p]==40));
   let mut n=node(&s,runout,&[]);for _ in 0..100 {if n.state.active_count()<2||actionable(&n.state).count_ones()<2{break;}if n.pending==0 {if n.street==5 {break;}n.street+=1;n.board=n.board.add(runout[n.street-1]);n.paid=[0;6];n.target=0;n.last_raise=2;n.raises=0;n.acted=0;n.bettor=None;n.pending=actionable(&n.state);continue;}let p=actor(&n);let a=actions(&n,p);let i=t.rng.gen_range(0..a.len());n=apply(&n,p,a[i],i);}
   let v=if n.state.active_count()==1 {n.state.payoff_fold((0..6).find(|&p|!n.state.folded[p]).unwrap() as u8)}else{n.state.payoff_showdown(runout.iter().fold(Hand::new(),|h,&c|h.add(c)))};assert!(v.iter().sum::<f32>().abs()<0.0001);assert!((0..6).all(|p|n.state.stacks[p]+n.state.bets[p]==40));
  }
 }
 #[test] fn raises_account_for_money_already_paid() {
  let mut s=PreflopState::new_6max(PreflopBetConfig::default());s.bets=[4,4,0,0,1,2];s.stacks=[36,36,40,40,39,38];s.folded=[false,false,true,true,true,true];
  let n=node(&s,[0,1,2,3,4],&[]);let a=apply(&n,0,6,1);let b=apply(&a,1,18,2);let c=apply(&b,0,18,1);assert_eq!(c.paid[0],18);assert_eq!(c.state.bets[0],22);assert_eq!(c.state.stacks[0],18);
 }
}
