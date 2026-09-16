"""Pinned LightGlue/SIFT adapter for experimental R3 scoring."""
from __future__ import annotations
import hashlib, sys, time, gc
from pathlib import Path

EXPECTED_SHA256 = "5b52b8d9982d43532dc042606b346bb9594c9f5a4bd6f64362c63866287b4ac0"
REPOSITORY = "cvg/LightGlue"
COMMIT = "edb2b838efb2ecfe3f88097c5fad9887d95aedad"

class LightGlueAdapterError(RuntimeError): pass
def sha256(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''): h.update(b)
 return h.hexdigest()

class LightGlueSiftAdapter:
 def __init__(self, model_path, repository_root, device='cpu', max_keypoints=512, pair_window=1):
  self.model_path=Path(model_path); self.repository_root=Path(repository_root); self.device=device
  self.max_keypoints=max_keypoints; self.pair_window=pair_window; self.started=time.perf_counter()
  if not self.model_path.is_file(): raise LightGlueAdapterError(f'model missing: {self.model_path}')
  actual=sha256(self.model_path)
  if actual != EXPECTED_SHA256: raise LightGlueAdapterError(f'model hash mismatch: {actual}')
  if str(self.repository_root) not in sys.path: sys.path.insert(0,str(self.repository_root))
  try:
   import torch
   torch.set_num_threads(1)
   from lightglue import LightGlue, SIFT
   from lightglue.utils import load_image
  except Exception as exc: raise LightGlueAdapterError(f'LightGlue dependencies unavailable: {exc}') from exc
  self.torch=torch; self.load_image=load_image
  try:
   self.extractor=SIFT(max_num_keypoints=max_keypoints).eval().to(device)
   self.matcher=LightGlue(features='sift').eval().to(device)
   state=torch.load(self.model_path,map_location=device,weights_only=True)
   self.matcher.load_state_dict(state,strict=False)
  except Exception as exc: raise LightGlueAdapterError(f'LightGlue model load failed: {exc}') from exc
  self.metadata={'model_path':str(self.model_path.resolve()),'model_sha256':actual,'repository':REPOSITORY,'commit':COMMIT,'device':device,'torch':torch.__version__,'max_keypoints':max_keypoints,'pair_window':pair_window,'preprocessing':'official load_image; SIFT extractor auto-resize; RGB float [0,1]','license':'Apache-2.0'}
 def pair_metrics(self, first, second):
  try:
   from lightglue.utils import rbd
   image0=self.load_image(str(first)); image1=self.load_image(str(second))
   if self.device != 'cpu': image0=image0.to(self.device); image1=image1.to(self.device)
   with self.torch.inference_mode():
    f0=self.extractor.extract(image0); f1=self.extractor.extract(image1); m=self.matcher({'image0':f0,'image1':f1})
   f0,f1,m=[rbd(x) for x in (f0,f1,m)]
   matches=int(m['matches'].shape[0]); conf=m.get('scores')
   confidence=float(conf.float().mean().item()) if conf is not None and conf.numel() else 0.0
   k0=int(f0['keypoints'].shape[0]); k1=int(f1['keypoints'].shape[0]); overlap=matches/max(1,min(k0,k1)); novelty=1.0-overlap
   result={'keypoints_first':k0,'keypoints_second':k1,'match_count':matches,'match_confidence':confidence,'overlap_score':overlap,'novelty_score':novelty}
   del image0, image1, f0, f1, m
   if self.device != 'cpu': self.torch.cuda.empty_cache()
   gc.collect()
   return result
  except Exception as exc: raise LightGlueAdapterError(f'feature matching failed: {exc}') from exc
