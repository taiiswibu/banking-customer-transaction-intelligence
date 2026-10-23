"""Optional developer check against cached official Microsoft JSON schemas.
Requires jsonschema (not required by the normal build). Does not execute Power BI.
"""
import json,warnings
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    import jsonschema
    from jsonschema import RefResolver
    store=json.loads((ROOT/'assets/schemas/all.json').read_text(encoding='utf-8'))
    results=[]
    files=list((ROOT/'powerbi').rglob('*.json'))+list((ROOT/'powerbi').rglob('*.pbir'))+list((ROOT/'powerbi').rglob('*.pbism'))
    for f in files:
        data=json.loads(f.read_text(encoding='utf-8'));u=data.get('$schema')
        if not u:continue
        schema=store[u]
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            v=jsonschema.Draft7Validator(schema,resolver=RefResolver(base_uri=u,referrer=schema,store=store))
            errors=[{'path':'/'.join(map(str,e.absolute_path)),'message':e.message} for e in v.iter_errors(data)]
        results.append({'file':f.relative_to(ROOT).as_posix(),'schema':u,'status':'FAIL' if errors else 'PASS','errors':errors})
    output={'status':'FAIL' if any(r['errors'] for r in results) else 'PASS','files_validated':len(results),
        'source':'Official Microsoft JSON schemas, cached 2026-10-23; structural validation only. No TMDL, M or DAX runtime validation.',
        'results':results}
    (ROOT/'reports/schema_validation.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    for r in results:
        if r['errors']:print(r['file'],json.dumps(r['errors'],indent=2))
    print(output['status'],len(results),'JSON schema validations')
    if output['status']!='PASS':raise SystemExit(1)

if __name__=='__main__':main()
