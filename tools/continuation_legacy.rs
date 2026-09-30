//! Joint external-sampling CFR over a bounded three-street continuation.
//! Each street allows check, 1/3-pot, 3/4-pot, or shove, then call/fold.
//! There are no postflop raises. Public texture and private made/draw features
//! are abstracted. This is an imperfect-recall approximation, not full NLHE.
//! No fixed position transfer or prescribed hand opening ranges are used.
use super::{PreflopState, PreflopTrainer, RegretEntry, NUM_PLAYERS};
use crate::card::{rank, suit, Card, Hand};
use crate::eval::{evaluate, HandRank};
use rand::Rng;

const ORDER: [usize; NUM_PLAYERS] = [4,5,0,1,2,3];

#[derive(Clone, Copy, Hash, Eq, PartialEq)]
pub(super) struct InfoKey(pub u64);

#[derive(Clone)]
struct Node {
    state: PreflopState,
    board: Hand,
    runout: [Card; 5],
    street: usize,
    checked: u8,
    pending: u8,
    bettor: Option<usize>,
    target: i32,
    bet_kind: u8,
    previous: u8,
}

fn actionable(state: &PreflopState) -> u8 {
    (0..NUM_PLAYERS).filter(|&p| !state.folded[p] && !state.all_in[p])
        .fold(0, |mask,p| mask | (1<<p))
}

fn wager(state: &mut PreflopState, p: usize, amount: i32) {
    let paid = amount.max(0).min(state.stacks[p]);
    state.stacks[p] -= paid;
    state.bets[p] += paid;
    state.all_in[p] = state.stacks[p] == 0;
}

fn actor(node: &Node) -> usize {
    let start=node.bettor.map(|p|(ORDER.iter().position(|&i|i==p).unwrap()+1)%6).unwrap_or(0);
    (0..6).map(|i|ORDER[(start+i)%6]).find(|&p|node.pending&(1<<p)!=0).unwrap()
}

fn amounts(pot: i32,stack: i32) -> Vec<i32> {
    let mut v=vec![0];
    for x in [(pot as f32/3.0).round() as i32,(pot as f32*0.75).round() as i32,stack] {
        let x=x.max(2).min(stack); // NLHE minimum bet = one BB, unless all-in.
        if !v.contains(&x) {v.push(x);}
    }
    v
}

/// Features use only the acting player's cards and the current public board.
fn features(hole: Hand, board: Hand, street: usize) -> (u8,u8,u8) {
    let mut br = [0u8;13];
    let mut full = [0u8;13];
    let mut suits = [0u8;4];
    let mut mask = 0u16;
    for c in board.iter() { br[rank(c) as usize]+=1; }
    full.copy_from_slice(&br);
    for c in hole.union(board).iter() {
        suits[suit(c) as usize]+=1;
        mask |= 1<<rank(c);
    }
    for c in hole.iter() { full[rank(c) as usize]+=1; }
    let cards: Vec<Card> = hole.iter().collect();
    let hi = cards.iter().map(|&c| rank(c)).max().unwrap();
    let lo = cards.iter().map(|&c| rank(c)).min().unwrap();
    let bh = board.iter().map(rank).max().unwrap();
    let private_pair = hi==lo;
    let paired_rank = (0..13).rev().find(|&r| full[r]>=2 && br[r]<full[r]);
    let made = match evaluate(hole.union(board)).hand_rank() {
        HandRank::StraightFlush => 15,
        HandRank::FourOfAKind => if br.iter().any(|&n| n==4) { 2 } else {14},
        HandRank::FullHouse => 13,
        HandRank::Flush => 12,
        HandRank::Straight => 11,
        HandRank::ThreeOfAKind => if br.iter().any(|&n| n==3) {2} else {10},
        HandRank::TwoPair => {
            if private_pair && br.iter().any(|&n|n>=2) {
                if hi>bh {8} else {4}
            } else if cards.iter().filter(|&&c|br[rank(c) as usize]>0).count()==2 {9}
            else if let Some(r)=paired_rank {if r as u8>=bh {7}else{5}} else {2}
        },
        HandRank::OnePair => if let Some(r)=paired_rank {
            if private_pair && hi>bh {8}
            else if r as u8 == bh {
                let kicker=cards.iter().map(|&c|rank(c)).filter(|&r2|r2!=r as u8).max().unwrap_or(0);
                if kicker>=10 {7}else{6}
            }
            else if private_pair {3} else {4}
        } else {2},
        HandRank::HighCard => if hi==12 {1}else{0},
    };
    let mut draw=0;
    if street<5 {
        let flush = hole.iter().any(|c|suits[suit(c) as usize]==4);
        let wheel=(mask<<1)|((mask>>12)&1);
        let straight=(0..=9).any(|low|((wheel>>low)&31).count_ones()>=4);
        draw=match (flush,straight) {(false,false)=>0,(false,true)=>1,(true,false)=>2,_=>3};
    }
    let paired=br.iter().any(|&n|n>=2);
    let max_suit=board.iter().fold([0u8;4],|mut a,c|{a[suit(c) as usize]+=1;a}).into_iter().max().unwrap();
    let texture=(paired as u8)*2+(max_suit>=3) as u8;
    (made,draw,texture)
}

fn key(node: &Node,p: usize,n: usize) -> InfoKey {
    let (made,draw,texture)=features(node.state.holes[p],node.board,node.street);
    let active=(0..NUM_PLAYERS).filter(|&i|!node.state.folded[i]).fold(0u8,|m,i|m|(1<<i));
    let pot: i32=node.state.bets.iter().sum();
    let spr=node.state.stacks[p] as f32/pot.max(1) as f32;
    let spr_bucket=if spr<0.5 {0}else if spr<1.0 {1}else if spr<2.0 {2}else if spr<4.0 {3}else{4};
    let mut value=made as u64;
    let fields=[(draw as u64,2),(texture as u64,2),(p as u64,3),
        ((node.street-3) as u64,2),(active as u64,6),(node.checked as u64,6),
        (node.bet_kind as u64,2),(node.bettor.unwrap_or(6) as u64,3),
        (node.state.n_raises.min(3) as u64,2),(spr_bucket,3),
        (node.state.last_aggressor.unwrap_or(6) as u64,3),
        (node.previous as u64,4),(n as u64,3)];
    let mut shift=4;
    for (field,bits) in fields {value|=field<<shift;shift+=bits;}
    InfoKey(value)
}

fn terminal(node: &Node,t: u8) -> f32 {
    if node.state.active_count()==1 {
        let winner=(0..NUM_PLAYERS).find(|&p|!node.state.folded[p]).unwrap();
        node.state.payoff_fold(winner as u8)[t as usize]
    } else {
        let board=node.runout.iter().fold(Hand::new(),|h,&c|h.add(c));
        node.state.payoff_showdown(board)[t as usize]
    }
}

fn cfr(trainer: &mut PreflopTrainer,node: &Node,t: u8) -> f32 {
    if node.state.folded[t as usize] {return -(node.state.bets[t as usize] as f32);}
    if node.state.active_count()<=1 {return terminal(node,t);}
    if node.pending==0 || actionable(&node.state).count_ones()<2 && node.bettor.is_none() {
        if node.street==5 || actionable(&node.state).count_ones()<2 {return terminal(node,t);}
        let mut next=node.clone();
        next.street+=1;
        next.board=next.board.add(next.runout[next.street-1]);
        next.previous=((node.previous<<2)|node.bet_kind)&15;
        next.checked=0;next.bettor=None;next.target=0;next.bet_kind=0;
        next.pending=actionable(&next.state);
        return cfr(trainer,&next,t);
    }
    let p=actor(node);
    let pot: i32=node.state.bets.iter().sum();
    // 0 means check/fold; facing a bet, 1 means call.
    let actions: Vec<i32>=if node.bettor.is_some() {vec![0,node.target]}
        else {amounts(pot,node.state.stacks[p])};
    let k=key(node,p,actions.len());
    let strategy=trainer.postflop.entry(k).or_insert_with(||RegretEntry::new(actions.len())).current_strategy();
    let apply=|a:usize| {
        let mut child=node.clone();
        child.pending&=!(1<<p);
        if node.bettor.is_some() {
            if a==0 {child.state.folded[p]=true;}
            else {wager(&mut child.state,p,node.target);}
        } else if a==0 {child.checked|=1<<p;}
        else {
            wager(&mut child.state,p,actions[a]);
            child.bettor=Some(p);child.target=actions[a];
            child.bet_kind=if actions[a]==node.state.stacks[p] {3}else if a==1 {1}else{2};
            child.pending=actionable(&child.state)&!(1<<p);
        }
        child
    };
    if p==t as usize {
        let values:Vec<f32>=(0..actions.len()).map(|a|cfr(trainer,&apply(a),t)).collect();
        let value: f32=values.iter().zip(&strategy).map(|(v,s)|v*s).sum();
        let weight=trainer.blueprint.iterations as f32+1.0;
        let entry=trainer.postflop.get_mut(&k).unwrap();
        for a in 0..actions.len() {
            entry.regrets[a]=(entry.regrets[a]+values[a]-value).max(0.0);
            entry.cum_strategy[a]+=weight*strategy[a];
        }
        value
    } else {
        let roll=trainer.rng.gen::<f32>();
        let mut sum=0.0;
        let a=strategy.iter().position(|s|{sum+=s;roll<sum}).unwrap_or(actions.len()-1);
        cfr(trainer,&apply(a),t)
    }
}

pub(super) fn terminal_value(trainer: &mut PreflopTrainer,state: &PreflopState,t: u8) -> f32 {
    if state.folded[t as usize] {return -(state.bets[t as usize] as f32);}
    let mut dead=state.holes.iter().fold(Hand::new(),|h,&hole|h.union(hole));
    let mut runout=[0;5];
    for c in &mut runout {*c=trainer.draw_excluding(dead);dead=dead.add(*c);}
    let board=runout[..3].iter().fold(Hand::new(),|h,&c|h.add(c));
    let node=Node{state:state.clone(),board,runout,street:3,checked:0,
        pending:actionable(state),bettor:None,target:0,bet_kind:0,previous:0};
    cfr(trainer,&node,t)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::card::card;
    use crate::preflop::PreflopBetConfig;
    #[test]
    fn features_only_use_visible_cards() {
        let hole=Hand::new().add(card(10,3)).add(card(3,3));
        let flop=Hand::new().add(card(0,3)).add(card(4,3)).add(card(9,1));
        let river=flop.add(card(12,3)).add(card(1,0));
        assert_ne!(features(hole,flop,3),features(hole,river,5));
    }
    #[test]
    fn top_pair_kicker_is_not_the_paired_card() {
        let flop=Hand::new().add(card(12,0)).add(card(5,1)).add(card(2,2));
        let weak=Hand::new().add(card(12,3)).add(card(0,3));
        let strong=Hand::new().add(card(12,3)).add(card(11,3));
        assert_eq!(features(weak,flop,3).0,6);
        assert_eq!(features(strong,flop,3).0,7);
    }
    #[test]
    fn minimum_bet_and_allin_exception() {
        assert_eq!(amounts(4,40),vec![0,2,3,40]);
        assert_eq!(amounts(4,1),vec![0,1]);
    }
    #[test]
    fn multiway_responses_start_after_bettor() {
        let mut node=Node{state:PreflopState::new_6max(PreflopBetConfig::default()),
            board:Hand::new(),runout:[0;5],street:3,checked:0,
            pending:(1<<3)|(1<<4)|(1<<5),bettor:Some(2),target:4,bet_kind:1,previous:0};
        assert_eq!(actor(&node),3); // BTN follows CO, before SB and BB.
        node.pending&=!(1<<3);
        assert_eq!(actor(&node),4);
    }
    #[test]
    fn check_call_and_fold_preserve_zero_sum() {
        let mut trainer=PreflopTrainer::new(PreflopBetConfig::default(),7);
        let mut state=PreflopState::new_6max(PreflopBetConfig::default());
        let mut dead=Hand::new();
        for p in 0..6 {
            let a=trainer.draw_excluding(dead);dead=dead.add(a);
            let b=trainer.draw_excluding(dead);dead=dead.add(b);
            state.holes[p]=Hand::new().add(a).add(b);
        }
        let mut board=Hand::new();
        for _ in 0..5 {let c=trainer.draw_excluding(dead);dead=dead.add(c);board=board.add(c);}
        wager(&mut state,0,10);wager(&mut state,1,10);
        state.folded[2]=true;
        assert!(state.payoff_showdown(board).iter().sum::<f32>().abs()<0.001);
    }
}
