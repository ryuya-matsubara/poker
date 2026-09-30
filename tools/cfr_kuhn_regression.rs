// Independent perfect-recall, two-player zero-sum benchmark for the actual
// regret and averaging kernel. This does NOT certify six-player NLHE.
#[cfg(test)]
mod kuhn_regression {
 use super::*;
 use rand::{SeedableRng,rngs::SmallRng};
 fn payoff(cards:[u8;2],h:&[u8],tr:usize)->Option<f32> {
  let win=if cards[0]>cards[1]{1.}else{-1.};
  let v=match h { [0,0]=>win,[1,0]=>1.,[0,1,0]=>-1.,[1,1]|[0,1,1]=>2.*win,_=>return None};
  Some(if tr==0 {v}else{-v})
 }
 fn index(cards:[u8;2],h:&[u8])->usize {
  let p=h.len()%2;let history=match h {[]=>0,[0]=>1,[1]=>2,[0,1]=>3,_=>unreachable!()};
  cards[p] as usize*4+history
 }
 fn traverse(e:&mut [RegretEntry],f:&[Vec<f32>],rng:&mut SmallRng,cards:[u8;2],h:&mut Vec<u8>,tr:usize,r:Reach,w:f64)->f32 {
  if let Some(v)=payoff(cards,h,tr){return v;}
  let p=h.len()%2;let k=index(cards,h);let s=&f[k];
  if p==tr {
   let common=rng.clone();let mut v=[0.;2];
   for a in 0..2 { *rng=common.clone();h.push(a as u8);v[a]=traverse(e,f,rng,cards,h,tr,Reach{own:r.own*s[a] as f64,..r},w);h.pop(); }
   let value=v[0]*s[0]+v[1]*s[1];update(&mut e[k],s,&v,value,r,w);value
  }else{
   let q=[0.95*s[0]+0.025,0.95*s[1]+0.025];let a=sample(&q,rng);let ratio=s[a] as f64/q[a] as f64;
   h.push(a as u8);let v=traverse(e,f,rng,cards,h,tr,Reach{q:r.q*q[a] as f64,cf:r.cf*ratio,..r},w);h.pop();v*ratio as f32
  }
 }
 fn value(cards:[u8;2],h:&mut Vec<u8>,s:&[Vec<f32>],br:Option<(usize,u8)>)->f64 {
  if let Some(v)=payoff(cards,h,0){return v as f64;}
  let p=h.len()%2;let k=index(cards,h);
  let pi=if let Some((who,bits))=br {if who==p {let slot=cards[p] as usize*2+usize::from(h.len()>1||h.as_slice()==[1]);let a=(bits>>slot)&1;[if a==0 {1.}else{0.},if a==1 {1.}else{0.}]}else{[s[k][0] as f64,s[k][1] as f64]}}else{[s[k][0] as f64,s[k][1] as f64]};
  let mut total=0.;for a in 0..2 {h.push(a as u8);total+=pi[a]*value(cards,h,s,br);h.pop();}total
 }
 fn exact(s:&[Vec<f32>],br:Option<(usize,u8)>)->f64 {
  let mut v=0.;for a in 0..3 {for b in 0..3 {if a!=b {v+=value([a,b],&mut Vec::new(),s,br)/6.;}}}v
 }
 #[test] fn sampled_kernel_converges_on_kuhn_with_exact_best_response() {
  let mut e:Vec<_>=(0..12).map(|_|RegretEntry::new(2)).collect();let mut deal=SmallRng::seed_from_u64(471);
  for it in 0..200000 {
   let a=deal.gen_range(0..3);let mut b=deal.gen_range(0..3);while a==b {b=deal.gen_range(0..3);}
   let f:Vec<_>=e.iter().map(|x|x.current_strategy()).collect();let mut decision=SmallRng::seed_from_u64(deal.gen());
   traverse(&mut e,&f,&mut decision,[a,b],&mut Vec::new(),it%2,Reach::root(),it as f64+1.);
  }
  let s:Vec<_>=e.iter().map(|x|x.average_strategy()).collect();
  let br0=(0..64).map(|bits|exact(&s,Some((0,bits)))).fold(f64::NEG_INFINITY,f64::max);
  let br1=(0..64).map(|bits|exact(&s,Some((1,bits)))).fold(f64::INFINITY,f64::min);
  let game_value=exact(&s,None);let nashconv=br0-br1;
  println!("Kuhn value={game_value:0.6}; exact two-player NashConv={nashconv:0.6}");
  assert!((game_value+1./18.).abs()<0.03,"Incorrect Kuhn value: {game_value}");
  assert!(nashconv<0.06,"Sampled regret/average kernel did not converge: {nashconv}");
 }
}

