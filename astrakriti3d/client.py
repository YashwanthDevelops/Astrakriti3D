import json, time
from pathlib import Path
import requests

class WebODMError(RuntimeError): pass
class WebODMClient:
    def __init__(self, config, session=None): self.c=config; self.s=session or requests.Session(); self.token=None
    def url(self, path): return self.c.base_url + "/api" + path
    def request(self, method, path, **kwargs):
        kwargs.setdefault("timeout", self.c.timeout); headers=kwargs.pop("headers",{}).copy()
        if self.token: headers["Authorization"]="JWT "+self.token
        # A timed-out POST may already have created a task. Never replay mutations.
        attempts = 2 if method.upper() in {'GET', 'HEAD'} else 1
        for attempt in range(attempts):
            try:
                r=self.s.request(method,self.url(path),headers=headers,**kwargs)
                if (attempt == 0 and method.upper() in {'GET', 'HEAD'} and self.token
                        and r.status_code in {401,403} and 'signature has expired' in r.text.lower()):
                    self.authenticate()
                    headers['Authorization']='JWT '+self.token
                    continue
                break
            except requests.Timeout as e:
                if attempt == attempts - 1: raise WebODMError(f"request timeout after {attempts} attempts") from e
            except requests.RequestException as e:
                if attempt == attempts - 1: raise WebODMError(f"request failed after {attempts} attempts: {redact(str(e))}") from e
        if r.status_code >= 400: raise WebODMError(f"HTTP {r.status_code}: {redact(r.text[:1000])}")
        return r
    def authenticate(self):
        r=self.s.post(self.url("/token-auth/"),data={"username":self.c.username,"password":self.c.password},timeout=self.c.timeout)
        if r.status_code>=400: raise WebODMError(f"authentication failed (HTTP {r.status_code})")
        try: self.token=r.json()["token"]
        except (ValueError,KeyError): raise WebODMError("authentication response did not contain a token")
    def find_or_create_project(self):
        data=self.request("GET","/projects/").json(); items=data if isinstance(data,list) else data.get("results",[])
        for p in items:
            if p.get("name")==self.c.project_name: return str(p["id"])
        return str(self.request("POST","/projects/",data={"name":self.c.project_name}).json()["id"])
    def submit_task(self, project_id, manifest, options, geo_txt=None):
        if geo_txt is not None:
            geo_path=Path(geo_txt)
            if not geo_path.is_file(): raise WebODMError(f"geo.txt does not exist: {geo_path}")
            lines=geo_path.read_text(encoding="utf-8").splitlines()
            if lines[:1] != ["EPSG:4326"]: raise WebODMError("geo.txt must begin with EPSG:4326")
            names=[Path(x['path']).name for x in manifest]
            records=[line.split() for line in lines[1:]]
            geo_names=[r[0] for r in records if r]
            if any(len(r)!=3 for r in records) or len(set(names))!=len(names) or sorted(geo_names)!=sorted(names):
                raise WebODMError('geo.txt entries must match submitted image identities exactly')
        files=[]
        try:
            for x in manifest: files.append(("images",(Path(x["path"]).name,open(x["path"],"rb"))))
            if geo_txt is not None: files.append(("images",("geo.txt",open(geo_path,"rb"))))
            r=self.request("POST",f"/projects/{project_id}/tasks/",files=files,data={"options":json.dumps(options)})
            body=r.json();
            if "id" not in body: raise WebODMError("task response missing id")
            return str(body["id"])
        finally:
            for _,(_,f) in files: f.close()
    def task(self,p,t):
        body=self.request("GET",f"/projects/{p}/tasks/{t}/").json()
        if not isinstance(body,dict): raise WebODMError("malformed task response: expected object")
        return body
    def output(self,p,t): return self.request("GET",f"/projects/{p}/tasks/{t}/output/").text
    def cancel(self,p,t): self.request("POST",f"/projects/{p}/tasks/{t}/cancel/")
    def download(self,p,t,asset,destination):
        r=self.request("GET",f"/projects/{p}/tasks/{t}/download/{asset}",stream=True); destination=Path(destination); destination.parent.mkdir(parents=True,exist_ok=True)
        with destination.open("wb") as f:
            for chunk in r.iter_content(1024*1024): f.write(chunk)
        return destination
def redact(s):
    import re
    return re.sub(r"(?i)(password|token)(\s*[:=]\s*)([^\s,;]+)", r"\1\2[redacted]", s)
