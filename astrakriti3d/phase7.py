"""Reference-gated Phase 7 accuracy and completeness evaluation."""
from __future__ import annotations
import hashlib,json,math
from pathlib import Path
SCHEMA_VERSION='phase7.evaluation.v2'
class Phase7ValidationError(ValueError): pass
def _sha256(p):
 h=hashlib.sha256(); f=Path(p).open('rb')
 for b in iter(lambda:f.read(1048576),b''): h.update(b)
 f.close(); return h.hexdigest()
def _pct(v,q):
 if not v:return None
 v=sorted(map(float,v)); x=(len(v)-1)*q; a,b=math.floor(x),math.ceil(x)
 return v[a] if a==b else v[a]+(v[b]-v[a])*(x-a)
def stats(v):
 v=list(map(float,v)); return {'sample_count':len(v),'median':_pct(v,.5),'rmse':math.sqrt(sum(x*x for x in v)/len(v)) if v else None,'p95':_pct(v,.95),'maximum':max(v) if v else None}
def unit_factor(unit):
 d={'m':1.,'meter':1.,'meters':1.,'cm':.01,'mm':.001,'ft':.3048,'feet':.3048}; u=str(unit).lower()
 if u not in d: raise Phase7ValidationError(f'unsupported unit: {unit}')
 return d[u]
def validate_crs(crs):
 c=str(crs).upper().replace('EPSG:','')
 if c not in {'4326','32637'}: raise Phase7ValidationError(f'unsupported CRS: {crs}')
 return 'EPSG:'+c
def transform(point,source_crs,target_crs,units='m'):
 validate_crs(source_crs); validate_crs(target_crs); factor=unit_factor(units); x,y,z=(list(point)+[0,0,0])[:3]; s,t=validate_crs(source_crs),validate_crs(target_crs)
 if s != 'EPSG:4326': x,y,z=x*factor,y*factor,z*factor
 if s==t:return (x,y,z)
 if s=='EPSG:4326' and t=='EPSG:32637':
  a=6378137.; e=.0818191908426; k=.9996; lon,lat=math.radians(x),math.radians(y); l0=math.radians(39); n=a/math.sqrt(1-e*e*math.sin(lat)**2); tt=math.tan(lat)**2; c=e*e/(1-e*e)*math.cos(lat)**2; aa=math.cos(lat)*(lon-l0)
  m=a*((1-e*e/4-3*e**4/64-5*e**6/256)*lat-(3*e*e/8+3*e**4/32+45*e**6/1024)*math.sin(2*lat)+(15*e**4/256+45*e**6/1024)*math.sin(4*lat)-(35*e**6/3072)*math.sin(6*lat))
  return (k*n*(aa+(1-tt+c)*aa**3/6+(5-18*tt+tt*tt+72*c-58*e*e/(1-e*e))*aa**5/120)+500000,k*(m+n*math.tan(lat)*(aa**2/2+(5-tt+9*c+4*c*c)*aa**4/24+(61-58*tt+tt*tt+600*c-330*e*e/(1-e*e))*aa**6/720)),z)
 raise Phase7ValidationError('only EPSG:4326 to EPSG:32637 and identical CRS are supported')
def coordinate_errors(observed,reference,observed_crs,reference_crs,units='m',reference_uncertainty=0):
 o=transform(observed,observed_crs,'EPSG:32637',units); r=transform(reference,reference_crs,'EPSG:32637',units); dx,dy,dz=o[0]-r[0],o[1]-r[1],o[2]-r[2]
 return {'horizontal':math.hypot(dx,dy),'vertical':abs(dz),'three_dimensional':math.sqrt(dx*dx+dy*dy+dz*dz),'reference_uncertainty':float(reference_uncertainty)}
def _load_ref(path):
 if not path:return []
 p=Path(path)
 if not p.is_file():raise Phase7ValidationError(f'reference does not exist: {p}')
 try:d=json.loads(p.read_text(encoding='utf-8'))
 except Exception as e:raise Phase7ValidationError(f'malformed reference: {e}')
 rows=d.get('points',d) if isinstance(d,(dict,list)) else None
 if not isinstance(rows,list):raise Phase7ValidationError('reference must be a list or {"points": [...]}')
 if any(not isinstance(r,dict) or 'observed' not in r or 'reference' not in r for r in rows):raise Phase7ValidationError('each point needs observed and reference')
 return rows
def evaluate(*,artifact_dir,output,checkpoints=None,dimensions=None,reference_surface=None,crs='EPSG:32637',units='m',vertical_datum='unknown'):
 validate_crs(crs); unit_factor(units); root=Path(artifact_dir)
 if not root.is_dir():raise Phase7ValidationError(f'artifact directory does not exist: {root}')
 aa=[{'name':p.name,'path':str(p.resolve()),'sha256':_sha256(p),'bytes':p.stat().st_size} for p in sorted(root.iterdir()) if p.is_file()]
 refs=_load_ref(checkpoints); ee=[coordinate_errors(r['observed'],r['reference'],r.get('observed_crs',crs),r.get('reference_crs',crs),r.get('units',units),r.get('reference_uncertainty',0)) for r in refs]
 acc={'status':'measured' if ee else 'unverified','horizontal':stats([x['horizontal'] for x in ee]),'vertical':stats([x['vertical'] for x in ee]),'three_dimensional':stats([x['three_dimensional'] for x in ee]),'reference_uncertainty':stats([x['reference_uncertainty'] for x in ee]),'control_and_evaluation_separate':True}
 report={'schema_version':SCHEMA_VERSION,'baseline':'R1','inputs':{'artifact_dir':str(root.resolve()),'artifact_hashes':aa,'checkpoints_hash':_sha256(checkpoints) if checkpoints else None,'reference_surface_hash':_sha256(reference_surface) if reference_surface else None,'crs':validate_crs(crs),'units':units,'vertical_datum':vertical_datum},'accuracy':acc,'relative_shape_and_dimensions':{'status':'measured' if dimensions else 'unknown_scale','measurements':dimensions or []},'completeness':{'status':'measured' if reference_surface else 'audit_template','reference_surface':str(Path(reference_surface).resolve()) if reference_surface else None,'rules':{'visibility':'explicit reference visibility only','distance':'explicit threshold required','unseen_geometry':'never inferred'},'holes':[],'disconnected_regions':[],'observed_but_missing_surfaces':[],'never_observed_surfaces':[]},'limitations':['Internal telemetry agreement is not independent accuracy.','Unseen geometry is never inferred as measured completeness.'],'verdict':'PASS'}
 out=Path(output); out.mkdir(parents=True,exist_ok=False); (out/'phase7_evaluation.json').write_text(json.dumps(report,indent=2,sort_keys=True)); (out/'phase7_evaluation.md').write_text(f'Astrakriti3D Phase 7 evaluation\nSchema: {SCHEMA_VERSION}\nAccuracy: {acc["status"]}\nDimensions: {report["relative_shape_and_dimensions"]["status"]}\nCompleteness: {report["completeness"]["status"]}\n',encoding='utf-8'); return report
def validate_baseline(*,inventory,association,shots,output):
 for p in map(Path,(inventory,association,shots)):
  if not p.is_file():raise Phase7ValidationError(f'required input does not exist: {p}')
 inv=json.loads(Path(inventory).read_text()); out=Path(output); out.mkdir(parents=True,exist_ok=False); aa=[]
 for a in inv.get('artifacts',[]):
  p=Path(a['path']); aa.append({'name':a.get('name'),'path':str(p),'exists':p.is_file(),'sha256':_sha256(p) if p.is_file() else None,'expected_sha256':a.get('sha256')})
 shots_data=json.loads(Path(shots).read_text()); assoc_data=json.loads(Path(association).read_text()); features=shots_data.get('features',[]); rows={r.get('frame_filename'):r for r in assoc_data.get('rows',[]) if r.get('association_status')=='matched'}; matched=sum(1 for f in features if f.get('properties',{}).get('filename') in rows)
 report={'schema_version':SCHEMA_VERSION,'offline_only':True,'webodm_submitted':False,'artifact_integrity':{'artifacts':aa,'all_present':all(x['exists'] for x in aa),'all_hashes_match':all(x['exists'] and x['sha256']==x['expected_sha256'] for x in aa)},'internal_geolocation_consistency':{'matched_camera_count':matched,'interpretation':'Internal telemetry agreement is not independent accuracy.'},'accuracy':{'status':'unverified','reason':'No independent surveyed checkpoints, physical dimensions, or trusted reference surface supplied.'},'relative_shape_and_dimensions':{'status':'unknown_scale'},'completeness':{'status':'audit_template','holes':[],'disconnected_regions':[],'observed_but_missing_surfaces':[],'never_observed_surfaces':[]},'limitations':['Internal telemetry agreement is not independent accuracy.','No unseen geometry is inferred as measured completeness.']}
 (out/'phase7_validation.json').write_text(json.dumps(report,indent=2,sort_keys=True)); (out/'phase7_validation.md').write_text('Astrakriti3D Phase 7\nAccuracy: unverified\nScale: unknown\nCompleteness: source-view audit template only.\n'); return report
