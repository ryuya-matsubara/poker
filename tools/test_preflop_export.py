"""Exercise binary export, normalization, and configuration rejection."""
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ExportTests(unittest.TestCase):
    def blueprint(self, path, bad=False):
        data = bytearray()
        def put(fmt, *values):
            data.extend(struct.pack('<'+fmt, *values))
        put('B',3)
        for sizes in [[4,5],[14],[28]]:
            put('B',len(sizes))
            put('i'*len(sizes),*sizes)
        put('BiBQQ',1,6,0,10000,169*6)
        for depth in range(6):
            for bucket in range(169):
                history=bytes(depth) if depth<5 else bytes([1,0,0])
                put('BH',bucket,len(history))
                data.extend(history)
                n=4
                put('H',n)
                put('f'*n,*([0]*n))
                values=list(range(1,n+1))
                if bad and depth==0 and bucket==139:
                    values[0]=float('nan')
                put('f'*n,*values)
        path.write_bytes(data)

    def run_export(self, folder):
        return subprocess.run([sys.executable,str(Path(__file__).with_name('export_preflop_policy.py')),
            str(folder/'blueprint.bin'),str(folder/'policy.json'),'--min-visits','0'],
            capture_output=True,text=True)

    def test_probability_and_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            self.blueprint(folder/'blueprint.bin')
            result=self.run_export(folder)
            self.assertEqual(result.returncode,0,result.stderr)
            policy=json.loads((folder/'policy.json').read_text())
            self.assertEqual(policy['min_allin_depth'],0)
            self.assertEqual(policy['max_stack_bb'],20)
            self.assertEqual(policy['oop_pot_tax'],0)
            for rows in policy['histories'].values():
                self.assertEqual(len(rows),169)
                for row in rows:
                    self.assertAlmostEqual(sum(row),1,places=3)
            self.assertEqual(len(policy['histories']['000000'][139]),4)
            self.assertEqual(len(policy['histories']['010000'][17]),4)

    def test_low_mass_shallow_histories_survive(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            self.blueprint(folder/'blueprint.bin')
            result=subprocess.run([sys.executable,str(Path(__file__).with_name('export_preflop_policy.py')),
                str(folder/'blueprint.bin'),str(folder/'policy.json'),'--max-histories','1'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            data=json.loads((folder/'policy.json').read_text())
            self.assertTrue(all(row is not None for row in data['histories']['010000']))

    def test_reject_nonfinite_probability(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            self.blueprint(folder/'blueprint.bin',bad=True)
            result=self.run_export(folder)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('Non-finite',result.stderr)


if __name__=='__main__':
    unittest.main()
