// Test the actual browser script and its action-history mapping without a browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto').webcrypto;

const html = fs.readFileSync('index.html', 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1].replace(
  '  newGame();',
  '  globalThis.hooks={newGame,handBucket,solverOptions,doAction,heroStrategyAdvice,getGame:()=>game};',
);
class Element {
  constructor() { this.children=[]; this.handlers={}; this.textContent=''; this.innerHTML=''; this.hidden=false; }
  append(x) { this.children.push(x); }
  addEventListener(k, f) { this.handlers[k] = f; }
}
const elements = new Map();
const document = {
  getElementById: id => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  },
  createElement: () => new Element(),
};
const policy = JSON.parse(fs.readFileSync('preflop_policy.json', 'utf8'));
const charts = JSON.parse(fs.readFileSync('preflop_charts.json', 'utf8'));
const context = {document, crypto, Uint32Array, Map, Set, Math, Intl,
  fetch: url => Promise.resolve({ok:true, json:()=>Promise.resolve(url.includes('policy')?policy:charts)}),
  setTimeout:()=>1, clearTimeout:()=>{}};
vm.runInNewContext(script, context);

(async () => {
  await new Promise(resolve => setImmediate(resolve));
  const {newGame,handBucket,solverOptions,doAction,heroStrategyAdvice,getGame} = context.hooks;
  assert.equal(handBucket([{r:12,s:'♠'},{r:5,s:'♥'}]), 139, 'Q5o canonical bucket');
  newGame();
  const game = getGame();
  assert.equal(game.actor, 3, 'UTG acts first');
  for (const id of [3,4,5]) doAction(game.players[id], 'fold');
  assert.equal(game.actor, 0, 'hero is BTN');
  assert.equal(game.solverHistory, '000000', 'three folds use action index 0');
  assert.deepEqual(Array.from(solverOptions(game.players[0]), a=>a.kind), ['fold','raise']);
  assert.equal(solverOptions(game.players[0])[1].target, 2500);
  assert.deepEqual(Array.from(solverOptions(game.players[1]), a=>a.kind), ['fold','call','raise']);
  assert.equal(solverOptions(game.players[1])[2].target, 3000);
  assert.deepEqual(Array.from(solverOptions(game.players[2]), a=>a.kind), ['check','raise']);
  game.currentBet = 2500; game.solverDepth = 1;
  assert.deepEqual(Array.from(solverOptions(game.players[0]), a=>a.kind), ['fold','call','raise','allin']);
  assert.equal(solverOptions(game.players[0])[2].target, 7000);
  game.players[0].cards = [{r:12,s:'♠'},{r:5,s:'♥'}];
  game.currentBet = 1000; game.solverDepth = 0;
  const advice = heroStrategyAdvice(game.players[0]);
  assert.match(advice,/参考戦略/);
  const chart = charts.find(s=>s.spot_name==='BTN RFI').hands.find(h=>h.hand==='Q5o');
  const root = policy.histories['000000'][139];
  assert.ok(Math.abs(root[1] - chart.actions.find(a=>a.action==='raise 5').prob) < .003,
    'UI policy and chart must agree for BTN Q5o');
  console.log('frontend preflop integration OK');
})().catch(error => {console.error(error);process.exitCode=1;});
