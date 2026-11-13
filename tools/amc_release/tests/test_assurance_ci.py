import tempfile
import unittest
from pathlib import Path
from tools.amc_release import assurance_ci


SRC='''name: AMC Assurance Pipeline
jobs:
  fault-injection:
    runs-on: ubuntu-latest
    steps:
      - name: Run fault injection tests
         run: |
          echo testing
      - name: Check SLO metrics
        run: |
          echo "Checking SLO metrics (placeholder - requires actual metrics collection)"
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - name: Run tests
        run: |
          python -m pytest tests/ --collect-only -q 2>&1 | tail -20 || true
  canary-deployment:
    runs-on: ubuntu-latest
    steps:
      - name: Canary status
        run: |
          echo "Canary deployment requires a real staging environment."
'''

class AssuranceCI(unittest.TestCase):
    def test_hardening_fixes_yaml_and_unmasks_pytest(self):
        revised=assurance_ci.harden(SRC)
        self.assertIn('        run: |',revised)
        self.assertNotIn('|| true',revised)
        self.assertIn('release BLOCKED',revised)
        self.assertEqual(revised.count('exit 1'),2)
        import yaml
        data=yaml.safe_load(revised)
        self.assertIn('fault-injection',data['jobs'])
    def test_idempotent(self):
        o=assurance_ci.harden(SRC)
        self.assertEqual(assurance_ci.harden(o),o)
    def test_unknown_fails_closed(self):
        with self.assertRaises(Exception):assurance_ci.harden('unknown workflow')
    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'ci.yml';f.write_text(SRC)
            self.assertTrue(assurance_ci.apply(f)['changed'])
            self.assertEqual(f.read_text(),SRC)
    def test_apply_makes_backup_and_no_double_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'ci.yml';f.write_text(SRC)
            self.assertTrue(assurance_ci.apply(f,check=False)['changed'])
            self.assertEqual(Path(str(f)+'.bak').read_text(),SRC)
            self.assertFalse(assurance_ci.apply(f)['changed'])

if __name__ == '__main__':unittest.main()
