"""Add complete, versioned trainer checkpoints after the immutable v7 patch.

The v7 blueprint is an export, NOT a resumable joint-CFR checkpoint.
This extension changes the chance RNG to a portable serializable ChaCha8 RNG;
new trajectories must start from zero. No v7 partial blueprint is imported.
"""
from pathlib import Path
import argparse
from patch_solver_base import replace_once

def extend(src):
    p = src / 'preflop.rs'
    text = p.read_text().replace('use rand::rngs::SmallRng;', 'use rand_chacha::ChaCha8Rng as SmallRng;')
    text = replace_once(text, 'let traverser = (i % NUM_PLAYERS as u64) as u8;',
                        'let traverser = (self.blueprint.iterations % NUM_PLAYERS as u64) as u8;')
    text += '\n' + Path(__file__).with_name('trainer_checkpoint.rs').read_text()
    p.write_text(text)
    p = src / 'continuation.rs'
    p.write_text(p.read_text().replace('use rand::rngs::SmallRng;', 'use rand_chacha::ChaCha8Rng as SmallRng;'))
    p = src.parent / 'Cargo.toml'
    p.write_text(p.read_text().replace('[dependencies]', '[dependencies]\nrand_chacha = { version = "0.3", features = ["serde1"] }\nflate2 = "1"', 1))
    p = src / 'main.rs'
    text = p.read_text()
    start = text.index('    if let Ok(prefix)=std::env::var("POKER_CHECKPOINT_PREFIX")')
    end = text.index('    if let Ok(path)=std::env::var("POKER_EV_OUTPUT")', start)
    text = text[:start] + '''    if let Ok(path)=std::env::var("POKER_RESUME") {
        trainer.load_joint_checkpoint(&path).expect("complete checkpoint required");
    }
    assert!(trainer.blueprint.iterations <= iterations);
    if let Ok(prefix)=std::env::var("POKER_CHECKPOINT_PREFIX") {
        trainer.train(iterations-trainer.blueprint.iterations);
        let stem=format!("{}/{}m",prefix,trainer.blueprint.iterations/1000000);
        std::fs::write(format!("{}-chart.json",stem),serde_json::to_string_pretty(&trainer.blueprint.extract_charts()).unwrap()).unwrap();
        let mut f=std::fs::File::create(format!("{}-blueprint.bin",stem)).unwrap();trainer.blueprint.save(&mut f).unwrap();
        trainer.diagnose_actions(&format!("{}-ev.json",stem),10000);
        trainer.save_joint_checkpoint(&format!("{}/joint-checkpoint.gz",prefix)).unwrap();
    } else {trainer.train(iterations-trainer.blueprint.iterations);}
''' + text[end:]
    p.write_text(text)

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source_dir',type=Path)
    extend(parser.parse_args().source_dir)
