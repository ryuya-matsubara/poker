// Full joint state, including chance RNG and postflop regrets/average mass.
// A blueprint alone must never be treated as a training checkpoint.
impl PreflopTrainer {
    pub fn save_joint_checkpoint(&self,path:&str)->std::io::Result<()> {
        use std::io::{Write,BufWriter};
        use byteorder::{LittleEndian,WriteBytesExt};
        let temporary=format!("{}.partial",path);
        let file=std::fs::File::create(&temporary)?;
        let mut w=flate2::write::GzEncoder::new(BufWriter::new(file),flate2::Compression::fast());
        w.write_all(b"JOINTCFR8\0")?;
        let rng=serde_json::to_vec(&self.rng)?;
        w.write_u32::<LittleEndian>(rng.len() as u32)?;w.write_all(&rng)?;
        w.write_u64::<LittleEndian>(self.board_samples as u64)?;
        w.write_f32::<LittleEndian>(self.oop_pot_tax)?;
        self.blueprint.save(&mut w)?;
        w.write_u64::<LittleEndian>(self.postflop.len() as u64)?;
        for (key,entry) in &self.postflop {
            w.write_u128::<LittleEndian>(key.0)?;
            for &x in entry.regrets.iter().chain(entry.cum_strategy.iter()) {w.write_f32::<LittleEndian>(x)?;}
        }
        let mut out=w.finish()?;out.flush()?;out.get_ref().sync_all()?;
        std::fs::rename(temporary,path)
    }
    pub fn load_joint_checkpoint(&mut self,path:&str)->std::io::Result<()> {
        use std::io::{Read,BufReader,Error,ErrorKind};
        use byteorder::{LittleEndian,ReadBytesExt};
        let mut r=flate2::read::GzDecoder::new(BufReader::new(std::fs::File::open(path)?));
        let mut magic=[0u8;10];r.read_exact(&mut magic)?;
        if &magic!=b"JOINTCFR8\0" {return Err(Error::new(ErrorKind::InvalidData,"not a complete v8 joint checkpoint"));}
        let size=r.read_u32::<LittleEndian>()? as usize;
        if size>4096{return Err(Error::new(ErrorKind::InvalidData,"bad RNG state length"));}
        let mut rng=vec![0;size];r.read_exact(&mut rng)?;
        let rng=serde_json::from_slice(&rng)?;
        let board_samples=r.read_u64::<LittleEndian>()? as usize;
        let tax=r.read_f32::<LittleEndian>()?;
        if tax!=0. {return Err(Error::new(ErrorKind::InvalidData,"position tax forbidden"));}
        let blueprint=PreflopBlueprint::load(&mut r)?;
        if blueprint.config.raise_sizes!=self.blueprint.config.raise_sizes || blueprint.config.sb_limp!=self.blueprint.config.sb_limp || blueprint.config.sb_open_size!=self.blueprint.config.sb_open_size || blueprint.config.min_allin_depth!=self.blueprint.config.min_allin_depth {
            return Err(Error::new(ErrorKind::InvalidData,"action tree mismatch"));
        }
        let count=r.read_u64::<LittleEndian>()? as usize;
        let mut postflop=HashMap::with_capacity(count);
        for _ in 0..count {
            let key=continuation::InfoKey(r.read_u128::<LittleEndian>()?);
            let mut entry=continuation::PostEntry{regrets:[0.;4],cum_strategy:[0.;4]};
            for x in entry.regrets.iter_mut().chain(entry.cum_strategy.iter_mut()) {*x=r.read_f32::<LittleEndian>()?;if !x.is_finite(){return Err(Error::new(ErrorKind::InvalidData,"nonfinite checkpoint"));}}
            if postflop.insert(key,entry).is_some(){return Err(Error::new(ErrorKind::InvalidData,"duplicate key"));}
        }
        let mut trailing=[0u8;1];if r.read(&mut trailing)?!=0{return Err(Error::new(ErrorKind::InvalidData,"trailing checkpoint data"));}
        self.blueprint=blueprint;self.postflop=postflop;self.rng=rng;self.board_samples=board_samples;self.oop_pot_tax=tax;
        self.post_strategy.clear();self.pre_strategy.clear();self.shared_runout=[0;5];Ok(())
    }
}
#[cfg(test)] mod joint_checkpoint_tests {
    use super::*;
    #[test] fn resumed_training_matches_uninterrupted_bit_for_bit() {
        let cfg=PreflopBetConfig{raise_sizes:vec![vec![4,5],vec![14],vec![28]],sb_limp:true,sb_open_size:Some(6),min_allin_depth:0};
        let mut a=PreflopTrainer::new(cfg.clone(),42);a.train(121);
        let path=std::env::temp_dir().join(format!("poker-joint-{}.gz",std::process::id()));
        a.save_joint_checkpoint(path.to_str().unwrap()).unwrap();
        let mut b=PreflopTrainer::new(cfg,999);b.load_joint_checkpoint(path.to_str().unwrap()).unwrap();
        a.train(173);b.train(173);
        assert_eq!(a.blueprint.iterations,b.blueprint.iterations);
        assert_eq!(a.blueprint.entries.len(),b.blueprint.entries.len());
        for (k,e) in &a.blueprint.entries {let f=&b.blueprint.entries[k];assert_eq!(e.regrets,f.regrets);assert_eq!(e.cum_strategy,f.cum_strategy);}
        assert_eq!(a.postflop.len(),b.postflop.len());
        for (k,e) in &a.postflop {let f=&b.postflop[k];assert_eq!(e.regrets,f.regrets);assert_eq!(e.cum_strategy,f.cum_strategy);}
        assert_eq!(a.rng.gen::<u64>(),b.rng.gen::<u64>());
        std::fs::remove_file(path).unwrap();
    }
    #[test] fn blueprint_is_rejected_as_resume_input() {
        let path=std::env::temp_dir().join(format!("poker-wrong-{}.gz",std::process::id()));
        std::fs::write(&path,b"not a complete checkpoint").unwrap();
        let mut t=PreflopTrainer::new(PreflopBetConfig::default(),1);
        assert!(t.load_joint_checkpoint(path.to_str().unwrap()).is_err());
        std::fs::remove_file(path).unwrap();
    }
}
