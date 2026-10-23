"""Execute every documented read-only business query and export results."""
import csv, re, sqlite3, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    con=sqlite3.connect(ROOT/'data/analytics.sqlite')
    target=ROOT/'reports/sql_results';target.mkdir(parents=True,exist_ok=True)
    s=(ROOT/'sql/analysis.sql').read_text(encoding='utf-8')
    parts=re.split(r'(?m)^-- (Q\d+): (.*)\n',s)
    manifest=[]
    for i in range(1,len(parts),3):
        key,title,sql=parts[i:i+3]
        cur=con.execute(sql.strip());rows=cur.fetchall()
        with (target/(key+'.csv')).open('w',encoding='utf-8',newline='') as f:
            w=csv.writer(f);w.writerow([x[0] for x in cur.description]);w.writerows(rows)
        manifest.append(dict(query=key,title=title,rows=len(rows),status='PASS'))
    (ROOT/'reports/sql_validation.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    con.close();print(f'Executed {len(manifest)} SQL business queries.')
    return manifest

if __name__=='__main__': main()
