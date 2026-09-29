//! Sampled, limited postflop continuation for preflop MCCFR terminals.
//!
//! Each sampled runout plays a single bet/call/fold decision on each street.
//! A decision sees only its own cards and the public cards available then.
//! This is a deliberately small behavioral abstraction, not a solved
//! equilibrium. It replaces a forced showdown plus a fixed position transfer.

use super::{PreflopState, PreflopTrainer, NUM_PLAYERS};
use crate::card::{rank, suit, Card, Hand};
use crate::eval::{evaluate, HandRank};
use rand::Rng;

const POSTFLOP_ORDER: [usize; NUM_PLAYERS] = [4, 5, 0, 1, 2, 3];

/// Hand/draw proxy based on cards currently visible to this player only.
/// Its purpose is to let weak hands relinquish equity to bets, while made
/// hands and draws continue. It does not inspect an opponent's hidden cards.
fn hand_signal(hole: Hand, board: Hand, street: usize) -> f32 {
    let full = hole.union(board);
    let made = evaluate(full).hand_rank();
    let board_high = board.iter().map(rank).max().unwrap_or(0);
    let hole_cards: Vec<Card> = hole.iter().collect();
    let hole_high = hole_cards.iter().map(|&c| rank(c)).max().unwrap_or(0);
    let pair = rank(hole_cards[0]) == rank(hole_cards[1]);
    let mut value = match made {
        HandRank::StraightFlush | HandRank::FourOfAKind | HandRank::FullHouse => 0.98,
        HandRank::Flush | HandRank::Straight => 0.94,
        HandRank::ThreeOfAKind => 0.89,
        HandRank::TwoPair => 0.79,
        HandRank::OnePair if pair && hole_high > board_high => 0.76,
        HandRank::OnePair if hole.iter().any(|c| rank(c) == board_high) => 0.67,
        HandRank::OnePair => 0.39,
        HandRank::HighCard => 0.08 + hole_high as f32 * 0.008,
    };
    if street < 5 {
        let mut suit_counts = [0;4];
        for c in full.iter() { suit_counts[suit(c) as usize] += 1; }
        if hole.iter().any(|c| suit_counts[suit(c) as usize] == 4) {
            value += if street == 3 { 0.22 } else { 0.15 };
        }
        let ranks: u16 = full.iter().fold(0, |mask, c| mask | (1 << rank(c)));
        let wheel = (ranks << 1) | ((ranks >> 12) & 1);
        let has_straight_draw = (0..=9).any(|low| ((wheel >> low) & 31).count_ones() >= 4);
        if has_straight_draw { value += if street == 3 { 0.14 } else { 0.09 }; }
    }
    value.min(0.99)
}

fn wager(state: &mut PreflopState, p: usize, amount: i32) -> i32 {
    let paid = state.stacks[p].min(amount.max(0));
    state.stacks[p] -= paid;
    state.bets[p] += paid;
    if state.stacks[p] == 0 { state.all_in[p] = true; }
    paid
}

fn play_street(state: &mut PreflopState, board: Hand, street: usize, rng: &mut impl Rng) {
    let players: Vec<usize> = POSTFLOP_ORDER.iter().copied()
        .filter(|&p| !state.folded[p] && !state.all_in[p]).collect();
    if players.len() < 2 { return; }
    let pot: i32 = state.bets.iter().sum();
    let count = state.active_count();
    let spr = players.iter().map(|&p| state.stacks[p]).min().unwrap_or(0) as f32 / pot.max(1) as f32;
    let bet_fraction = match street { 3 => 0.34, 4 => 0.50, _ => 0.66 };
    // Higher preflop investment and lower SPR make one pair more valuable.
    let commitment = if state.n_raises >= 2 && spr < 2.0 { 0.06 } else { 0.0 };
    let mut bettor = None;
    let mut bet = 0;
    for &p in &players {
        let signal = hand_signal(state.holes[p], board, street) + commitment;
        let propensity = if signal >= 0.79 { 0.78 } else if signal >= 0.56 { 0.57 }
            else if signal >= 0.28 && street < 5 { 0.22 } else { 0.065 };
        let multiway = (1.0 - 0.14 * (count.saturating_sub(2)) as f32).max(0.40);
        if rng.gen::<f32>() < propensity * multiway {
            let target = ((pot as f32 * bet_fraction).round() as i32).max(1);
            bet = wager(state, p, target);
            bettor = Some(p);
            break;
        }
    }
    let Some(aggressor) = bettor else { return; };
    // Every other non-all-in player faces exactly one decision, including
    // earlier checkers. All-ins already in the pot remain eligible at showdown.
    for &p in &players {
        if p == aggressor || state.folded[p] { continue; }
        let call = bet.min(state.stacks[p]);
        let odds = call as f32 / (state.bets.iter().sum::<i32>() + call).max(1) as f32;
        let signal = hand_signal(state.holes[p], board, street) + commitment;
        let threshold = 0.21 + odds * 0.75 + 0.06 * (count.saturating_sub(2)) as f32;
        let call_chance = (0.48 + (signal - threshold) * 2.3).clamp(0.02, 0.99);
        if rng.gen::<f32>() < call_chance { wager(state, p, call); }
        else { state.folded[p] = true; }
    }
}

pub(super) fn terminal_value(trainer: &mut PreflopTrainer, state: &PreflopState, traverser: u8) -> f32 {
    let mut dead = Hand::new();
    for p in 0..NUM_PLAYERS { dead = dead.union(state.holes[p]); }
    let mut total = 0.0;
    for _ in 0..trainer.board_samples {
        let mut board = Hand::new();
        let mut used = dead;
        let mut runout = [0;5];
        for card in &mut runout {
            *card = trainer.draw_excluding(used);
            used = used.add(*card);
        }
        let mut continued = state.clone();
        for (i, card) in runout.iter().enumerate() {
            board = board.add(*card);
            if i >= 2 && continued.active_count() > 1 {
                play_street(&mut continued, board, i + 1, &mut trainer.rng);
            }
        }
        let payoffs = if continued.active_count() == 1 {
            let winner = (0..NUM_PLAYERS).find(|&p| !continued.folded[p]).unwrap();
            continued.payoff_fold(winner as u8)
        } else { continued.payoff_showdown(board) };
        total += payoffs[traverser as usize];
    }
    total / trainer.board_samples as f32
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::card::card;
    use crate::preflop::PreflopBetConfig;

    #[test]
    fn future_cards_do_not_enter_flop_decision() {
        let hole = Hand::new().add(card(10,0)).add(card(3,1));
        let flop = Hand::new().add(card(1,2)).add(card(5,0)).add(card(9,1));
        let river = flop.add(card(12,3)).add(card(0,0));
        assert!(hand_signal(hole,flop,3) < 0.5);
        assert_ne!(hand_signal(hole,flop,3),hand_signal(hole,river,5));
    }

    #[test]
    fn continuation_preserves_chips() {
        let mut trainer = PreflopTrainer::new(PreflopBetConfig::default(), 7);
        let mut state = PreflopState::new_6max(PreflopBetConfig::default());
        let mut dead = Hand::new();
        for p in 0..NUM_PLAYERS {
            let c1 = trainer.draw_excluding(dead); dead = dead.add(c1);
            let c2 = trainer.draw_excluding(dead); dead = dead.add(c2);
            state.holes[p] = Hand::new().add(c1).add(c2);
        }
        let mut board = Hand::new();
        for street in 3..=5 {
            while board.count() < street as u32 {
                let c = trainer.draw_excluding(dead); dead = dead.add(c); board = board.add(c);
            }
            play_street(&mut state, board, street, &mut trainer.rng);
        }
        let payoffs = if state.active_count() == 1 {
            let winner = (0..NUM_PLAYERS).find(|&p| !state.folded[p]).unwrap();
            state.payoff_fold(winner as u8)
        } else { state.payoff_showdown(board) };
        assert!(payoffs.iter().sum::<f32>().abs() < 0.001);
    }
}
