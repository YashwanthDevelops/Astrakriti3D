"""Run the optional R3 selector; no model download or WebODM submission."""
import argparse, json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from astrakriti3d.r3_selection import select_r3

def main():
 p=argparse.ArgumentParser(); p.add_argument('--manifest',required=True); p.add_argument('--frames',required=True); p.add_argument('--output',required=True); p.add_argument('--geo-txt'); p.add_argument('--model'); p.add_argument('--device',default='cpu'); p.add_argument('--similarity-threshold',type=float,default=.995); p.add_argument('--max-gap-seconds',type=float,default=2.)
 a=p.parse_args(); r=select_r3(a.manifest,a.frames,a.output,a.geo_txt,a.model,a.device,a.similarity_threshold,a.max_gap_seconds); print(json.dumps(r,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
