"""Run the controlled R1/R2 WebODM experiment with identical options."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from astrakriti3d.config import Config
from astrakriti3d.runner import run
from astrakriti3d.selection_preflight import validate_selection

def main():
    p=argparse.ArgumentParser(); p.add_argument('--r1-images',required=True); p.add_argument('--r2-images',required=True); p.add_argument('--geo-txt',required=True); p.add_argument('--output',required=True); p.add_argument('--options')
    a=p.parse_args(); options=json.loads(Path(a.options).read_text()) if a.options else []
    root=Path(a.output); root.mkdir(parents=True,exist_ok=False); results={}
    for arm,images in (('R1',a.r1_images),('R2',a.r2_images)):
        arm_out=root/arm
        arm_geo=a.geo_txt
        if arm=='R2':
            selected={p.name for p in Path(images).iterdir() if p.is_file()}
            lines=Path(a.geo_txt).read_text(encoding='utf-8').splitlines()
            if not lines or lines[0] != 'EPSG:4326': raise ValueError('geo.txt must begin with EPSG:4326')
            filtered=[lines[0]]+[line for line in lines[1:] if line.split()[0] in selected]
            if len(filtered)-1 != len(selected): raise ValueError('R2 geo.txt does not cover every selected image')
            arm_out.mkdir(parents=True,exist_ok=True); arm_geo=str(arm_out/'geo.txt'); Path(arm_geo).write_text('\n'.join(filtered)+'\n',encoding='utf-8')
        arm_out.mkdir(parents=True,exist_ok=True)
        check=validate_selection(images,arm_geo)
        (arm_out/'selection_preflight.json').write_text(json.dumps(check,indent=2))
        if not check['valid']: raise ValueError(f'{arm} image/geo preflight failed; see selection_preflight.json')
        results[arm]=run(Config.from_env(),images,arm_out,options,geo_txt=arm_geo)
        (arm_out/'experiment_result.json').write_text(json.dumps(results[arm],indent=2))
    Path(a.output,'experiment_result.json').write_text(json.dumps({'schema_version':'phase6.experiment.v1','arms':results},indent=2)); print(json.dumps(results,indent=2))
    return 0 if all(x.get('ok') for x in results.values()) else 2
if __name__=='__main__': sys.exit(main())
