"""Patch the pinned upstream solver with 20BB and sampled continuation.

This intentionally operates on the exact pinned source, refusing changed
markers so an upstream update cannot silently change the trained game.
"""
import argparse
from pathlib import Path


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'expected exactly one upstream marker: {old[:80]!r}')
    return text.replace(old, new)


def patch(source_dir):
    file = source_dir / 'preflop.rs'
    source = file.read_text()
    source = replace_once(source,
        'let mut stacks = [200; NUM_PLAYERS]; // 100bb = 200 chips',
        'let mut stacks = [40; NUM_PLAYERS]; // 20bb = 40 half-BB chips')
    source = replace_once(source, 'stacks[4] = 200 - 1;', 'stacks[4] = 40 - 1;')
    source = replace_once(source, 'stacks[5] = 200 - 2;', 'stacks[5] = 40 - 2;')
    source = replace_once(source, 'board_samples: 10,', 'board_samples: 3,')
    source = replace_once(source, 'oop_pot_tax: 0.20,', 'oop_pot_tax: 0.0,')
    start = '            PreflopNodeType::TerminalShowdown => {'
    end = '            PreflopNodeType::Decision(player) => {'
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError('terminal node source changed')
    before, rest = source.split(start, 1)
    _old_terminal, after = rest.split(end, 1)
    source = before + start + '\n                continuation::terminal_value(self, state, traverser)\n            }\n' + end + after
    source = replace_once(source, 'use std::collections::HashMap;',
        'use std::collections::HashMap;\n#[path = "continuation.rs"] mod continuation;')
    # The upstream side-pot test assumes 100BB despite our 20BB patch.
    source = replace_once(source, 'state.stacks[0] = 50; // UTG 50 chips behind',
        'state.stacks[0] = 50; // explicit side-pot fixture\n        state.stacks[4] = 199;\n        state.stacks[5] = 198;')
    for old, new in [('assert_eq!(state.stacks[4], 199);', 'assert_eq!(state.stacks[4], 39);'),
                     ('assert_eq!(state.stacks[5], 198);', 'assert_eq!(state.stacks[5], 38);'),
                     ('assert_eq!(state.stacks[0], 200);', 'assert_eq!(state.stacks[0], 40);')]:
        source = replace_once(source, old, new)
    source += '''
#[cfg(test)]
mod poker_app_regression_tests {
    use super::*;

    #[test]
    fn six_max_20bb_blinds_and_action_order() {
        let cfg = PreflopBetConfig {
            raise_sizes: vec![vec![5], vec![14], vec![28]],
            sb_limp: true, sb_open_size: Some(6), min_allin_depth: 1,
        };
        let mut state = PreflopState::new_6max(cfg);
        assert_eq!(state.stacks, [40,40,40,40,39,38]);
        assert_eq!(state.bets, [0,0,0,0,1,2]);
        assert_eq!(state.actions(), vec![PreflopAction::Fold,PreflopAction::Raise(5)]);
        for _ in 0..3 { state = state.apply(PreflopAction::Fold); }
        assert_eq!(state.to_act, 3); // BTN after UTG, HJ, CO folds
        assert_eq!(state.actions(), vec![PreflopAction::Fold,PreflopAction::Raise(5)]);
        state = state.apply(PreflopAction::Raise(5));
        assert_eq!(state.actions(), vec![PreflopAction::Fold,PreflopAction::Call,
            PreflopAction::Raise(14),PreflopAction::AllIn]);
    }
}
'''
    file.write_text(source)
    (source_dir / 'continuation.rs').write_text(Path(__file__).with_name('continuation.rs').read_text())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source_dir', type=Path)
    patch(parser.parse_args().source_dir)
