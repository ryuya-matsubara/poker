"""Add only a spot-specific frozen-policy EV diagnostic; never change training or frequencies."""
from pathlib import Path
import sys
p=Path(sys.argv[1])/'continuation.rs'
s=p.read_text()
start=s.index('pub(super) fn diagnose(');end=s.index('\npub(super) fn terminal_value',start)
block=s[start:end]
old='[("BTN RFI","AQo"),("BTN RFI","AA"),("BTN RFI","A5s"),("BTN RFI","22"),("BTN RFI","Q5o"),("UTG 2BB -> BTN","53s"),("UTG 2BB -> BTN","AQo")]'
assert old in block
block=block.replace(old,'[("MP 2.5BB -> CO","TT")]')
block=block.replace('holes[3].iter()','holes[2].iter()')
block=block.replace('let prefix=if spot=="BTN RFI"{vec![0,0,0]}else{vec![1,0,0]};','let prefix=vec![0,2];')
block=block.replace('pre(t,&s.apply(x),3,','pre(t,&s.apply(x),2,')
block=block.replace('SmallRng::seed_from_u64(9127)','SmallRng::seed_from_u64(std::env::var("POKER_DIAG_SEED").ok().and_then(|v|v.parse().ok()).unwrap_or(9127))')
assert 'holes[3]' not in block and 'pre(t,&s.apply(x),3,' not in block
assert 'let prefix=vec![0,2];' in block
s=s[:start]+block+s[end:];p.write_text(s)
