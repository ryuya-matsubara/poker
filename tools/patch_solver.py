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
    source = replace_once(source, 'board_samples: 10,', 'board_samples: 1,')
    source = replace_once(source, 'oop_pot_tax: 0.20,', 'oop_pot_tax: 0.0,')
    source = replace_once(source, '    pub last_raise_size: i32,',
        '    pub last_raise_size: i32,\n    pub last_aggressor: Option<u8>,')
    source = replace_once(source, 'last_raise_size: 2, // BB = 2 chips as min raise reference',
        'last_raise_size: 2, // BB = 2 chips as min raise reference\n            last_aggressor: None,')
    source = replace_once(source, '            last_raise_size: 2,\n        }',
        '            last_raise_size: 2,\n            last_aggressor: None,\n        }')
    source = replace_once(source, 's.n_raises += 1;\n                s.last_raise_size = raise_size;',
        's.n_raises += 1;\n                s.last_aggressor = Some(p as u8);\n                s.last_raise_size = raise_size;')
    source = replace_once(source, 's.n_raises += 1;\n                        s.last_raise_size = raise_size;',
        's.n_raises += 1;\n                        s.last_aggressor = Some(p as u8);\n                        s.last_raise_size = raise_size;')
    start = '            PreflopNodeType::TerminalShowdown => {'
    end = '            PreflopNodeType::Decision(player) => {'
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError('terminal node source changed')
    before, rest = source.split(start, 1)
    _old_terminal, after = rest.split(end, 1)
    source = before + start + '\n                continuation::terminal_value(self, state, traverser)\n            }\n' + end + after
    source = replace_once(source, 'use std::collections::HashMap;',
        'use std::collections::HashMap;\n#[path = "continuation.rs"] mod continuation;')
    source = replace_once(source, '    pub oop_pot_tax: f32,',
        '    pub oop_pot_tax: f32,\n    postflop: HashMap<continuation::InfoKey, RegretEntry>,')
    source = replace_once(source, '            oop_pot_tax: 0.0,',
        '            oop_pot_tax: 0.0,\n            postflop: HashMap::new(),')
    source = replace_once(source,
        '"  iteration {}/{} ({} info sets)",\n                    i, iterations, self.blueprint.entries.len()',
        '"  iteration {}/{} ({} preflop, {} postflop info sets)",\n                    i, iterations, self.blueprint.entries.len(), self.postflop.len()')
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
            sb_limp: true, sb_open_size: Some(6), min_allin_depth: 0,
        };
        let mut state = PreflopState::new_6max(cfg);
        assert_eq!(state.stacks, [40,40,40,40,39,38]);
        assert_eq!(state.bets, [0,0,0,0,1,2]);
        assert_eq!(state.actions(), vec![PreflopAction::Fold,PreflopAction::Raise(5),PreflopAction::AllIn]);
        for _ in 0..3 { state = state.apply(PreflopAction::Fold); }
        assert_eq!(state.to_act, 3); // BTN after UTG, HJ, CO folds
        assert_eq!(state.actions(), vec![PreflopAction::Fold,PreflopAction::Raise(5),PreflopAction::AllIn]);
        state = state.apply(PreflopAction::Raise(5));
        assert_eq!(state.last_aggressor, Some(3));
        assert_eq!(state.actions(), vec![PreflopAction::Fold,PreflopAction::Call,
            PreflopAction::Raise(14),PreflopAction::AllIn]);
    }
}
'''
    file.write_text(source)
    (source_dir / 'continuation.rs').write_text(Path(__file__).with_name('continuation.rs').read_text())
    main = source_dir / 'main.rs'
    main_source = replace_once(main.read_text(),
        'min_allin_depth: 1,  // No open-shove; all-in allowed after first raise',
        'min_allin_depth: 0,  // Allow 20BB open shove')
    main_source = replace_once(main_source,
        '#[arg(long, default_value_t = 0.20)]',
        '#[arg(long, default_value_t = 0.0)]')
    main_source = replace_once(main_source,
        '    println!("Training 6-max preflop MCCFR:");',
        '    assert!(oop_pot_tax == 0.0, "Fixed OOP tax is disabled in the continuation model");\n    println!("Training 6-max preflop MCCFR:");')
    main.write_text(main_source)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source_dir', type=Path)
    patch(parser.parse_args().source_dir)
