"""Independent data reconciliation and Power BI structural/binding checks.
This does not execute the Power BI engine, M or DAX.
"""
import json,csv,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    checks=[]
    def check(name,condition,detail=''):
        checks.append(dict(check=name,status='PASS' if condition else 'FAIL',detail=detail))
        if not condition: raise AssertionError(name+': '+detail)
    m=json.loads((ROOT/'reports/metrics.json').read_text())
    con=sqlite3.connect(ROOT/'data/analytics.sqlite')
    def scalar(s):return con.execute(s).fetchone()[0]
    check('join_grain',scalar('SELECT COUNT(*) FROM v_transactions')==m['attempts'])
    check('sum_positive_cents',scalar('SELECT SUM(AmountCents) FROM FactTransaction WHERE HasError=0 AND AmountCents>0')==m['positive_cents'])
    check('sum_net_cents',scalar('SELECT SUM(AmountCents) FROM FactTransaction WHERE HasError=0')==m['net_cents'])
    check('error_denominator',scalar('SELECT SUM(HasError) FROM FactTransaction')==m['error_attempts'])
    check('error_bridge',scalar('SELECT COUNT(*) FROM FactError')==m['error_mentions'])
    check('distinct_error_tokens',scalar('SELECT COUNT(*) FROM (SELECT TransactionID,Error,COUNT(*) n FROM FactError GROUP BY 1,2 HAVING n>1)')==0)
    check('review_union',scalar('SELECT COUNT(*) FROM FactTransaction WHERE HighValueFlag=1 OR MultiStateFlag=1 OR ErrorBurstFlag=1')==m['review_attempts'])
    # Independent relational calculation for the spatial rule, rather than reusing pipeline sets.
    expected={r[0] for r in con.execute('''SELECT t.TransactionID FROM FactTransaction t JOIN
      (SELECT CardID,Date FROM FactTransaction WHERE IsPhysicalUS=1 GROUP BY CardID,Date HAVING COUNT(DISTINCT MerchantState)>=2) a
      ON t.CardID=a.CardID AND t.Date=a.Date WHERE t.IsPhysicalUS=1''')}
    actual={r[0] for r in con.execute('SELECT TransactionID FROM FactTransaction WHERE MultiStateFlag=1')}
    check('multistate_independent_sql',expected==actual)
    with (ROOT/'reports/sql_results/Q21.csv').open(newline='',encoding='utf-8') as f:expected={int(r['TransactionID']) for r in csv.DictReader(f)}
    actual={r[0] for r in con.execute('SELECT TransactionID FROM FactTransaction WHERE ErrorBurstFlag=1')}
    check('rolling_errors_independent_sql',expected==actual)
    check('high_value_sql',scalar('''SELECT COUNT(*) FROM FactTransaction t JOIN DimMCC m USING(MCC)
      WHERE (t.HighValueFlag=1) != (t.HasError=0 AND t.AmountCents>0 AND m.ReferenceCount>=30 AND t.AmountCents>m.P99Amount*100)''')==0)
    # Regression boundary fixtures for the SQL window predicate: inclusive 60 min, excluding future ties.
    fixture=[('2024-01-01 10:00:00',1),('2024-01-01 10:30:00',2),('2024-01-01 11:00:00',3),('2024-01-01 11:00:00',4)]
    con.execute('CREATE TEMP TABLE boundary(Timestamp TEXT,ID INTEGER)');con.executemany('INSERT INTO boundary VALUES (?,?)',fixture)
    observed=list(con.execute("SELECT a.ID,COUNT(b.ID) FROM boundary a JOIN boundary b ON b.Timestamp>=datetime(a.Timestamp,'-60 minutes') AND (b.Timestamp<a.Timestamp OR (b.Timestamp=a.Timestamp AND b.ID<=a.ID)) GROUP BY a.ID ORDER BY a.ID"))
    check('rolling_window_boundary_fixture',observed==[(1,1),(2,2),(3,3),(4,4)])
    manifest=json.loads((ROOT/'reports/model_manifest.json').read_text());tables=manifest['tables'];measures=set(manifest['measures'])
    model_dir=ROOT/'powerbi/Banking.SemanticModel/definition'
    model_tmdl=(model_dir/'model.tmdl').read_text(encoding='utf-8')
    measures_tmdl=(model_dir/'tables/KPI_Measures.tmdl')
    check('powerbi_valid_measure_table_name',
          measures_tmdl.is_file() and 'ref table KPI_Measures' in model_tmdl
          and 'ref table Measures\n' not in model_tmdl
          and measures_tmdl.read_text(encoding='utf-8').startswith('table KPI_Measures\n'))
    check('no_obsolete_measures_table',(model_dir/'tables/Measures.tmdl').exists() is False)
    definition=ROOT/'powerbi/Banking.Report/definition'
    files=list((ROOT/'powerbi').rglob('*.json'))+list((ROOT/'powerbi').rglob('*.pbip'))+list((ROOT/'powerbi').rglob('*.pbir'))+list((ROOT/'powerbi').rglob('*.pbism'))
    for f in files:json.loads(f.read_text(encoding='utf-8'))
    check('json_parse',True,str(len(files))+' files')
    def walk(value):
        if isinstance(value,dict):
            for typ in ['Column','Measure']:
                if typ in value:
                    o=value[typ];t=o.get('Expression',{}).get('SourceRef',{}).get('Entity');p=o.get('Property')
                    if t and p:
                        check('binding_'+t+'_'+p,(t=='KPI_Measures' and typ=='Measure' and p in measures) or (t in tables and p in tables[t]))
            for v in value.values():walk(v)
        elif isinstance(value,list):
            for v in value:walk(v)
    pages=json.loads((definition/'pages/pages.json').read_text())['pageOrder'];count=0
    for pid in pages:
        d=definition/'pages'/pid;page=json.loads((d/'page.json').read_text());ids=[]
        for f in d.glob('visuals/*/visual.json'):
            v=json.loads(f.read_text());ids.append(v['name']);count+=1;p=v['position']
            check('bounds_'+v['name'],p['x']>=0 and p['y']>=0 and p['x']+p['width']<=page['width'] and p['y']+p['height']<=page['height'])
            walk(v)
        check('unique_visuals_'+pid,len(ids)==len(set(ids)))
    check('page_count',len(pages)==4)
    for f,fc,t,tc in manifest['relationships']:
        check('relationship_uniqueness_'+t+tc,scalar(f'SELECT COUNT(*)-COUNT(DISTINCT "{tc}") FROM "{t}"')==0)
    check('all_sql_queries',len(json.loads((ROOT/'reports/sql_validation.json').read_text()))==26)
    check('preview_self_contained','__DATA__' not in (ROOT/'reports/dashboard_preview.html').read_text(encoding='utf-8'))
    con.close()
    result=dict(status='PASS',checks=checks,page_count=len(pages),visual_count=count,measure_count=len(measures),
      power_bi_desktop_runtime='NOT TESTED: Windows Power BI Desktop is unavailable in the build environment.',
      tmdl_m_dax_execution='NOT TESTED: structural checks are not a semantic engine evaluation.')
    (ROOT/'reports/validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(f'Validation PASS: {len(checks)} checks. Desktop/DAX/M execution still requires Power BI Desktop.')
    return result

if __name__=='__main__':main()
