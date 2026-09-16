import importlib.util
from pathlib import Path

path = Path(__file__).with_name('submit_coverage_aware_webodm.py')
spec = importlib.util.spec_from_file_location('coverage_submit', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.OUT = Path(__file__).resolve().parents[1] / 'evidence/phase19/lightweight-20260915-v4/webodm'
module.INPUT = Path(__file__).resolve().parents[1] / 'evidence/phase19/lightweight-20260915-v4'
module.main()
