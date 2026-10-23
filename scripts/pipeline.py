"""Rebuild deterministic analytical tables and SQLite database (standard library)."""
from __future__ import annotations
import csv, json, sqlite3, hashlib, math
from pathlib import Path
from collections import Counter, defaultdict, deque
from datetime import datetime, date, timedelta
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw'
OUT = ROOT / 'data/processed'

def read_csv(name):
    with (RAW / (name + '.csv')).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def write_csv(name, rows):
    rows = list(rows)
    if not rows: raise ValueError('Empty output: ' + name)
    with (OUT / (name + '.csv')).open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def money(x):
    return int((Decimal(str(x).replace('$','').replace(',','')) * 100).quantize(Decimal('1')))

def quantile(values, q):
    a = sorted(values); k = (len(a)-1)*q; lo = math.floor(k); hi = math.ceil(k)
    return a[lo] + (a[hi]-a[lo])*(k-lo)

def merchant_group(desc):
    s = desc.lower()
    groups = [
        ('Transfers & cash', ['money transfer','automated cash','financial institution']),
        ('Groceries & wholesale', ['grocery','supermarket','wholesale']),
        ('Food & dining', ['restaurant','eating place','fast food','drinking place','bakery']),
        ('Fuel & automotive', ['service station','fuel','automotive','motor vehicle','tire','parking']),
        ('Health & pharmacy', ['drug store','pharmac','hospital','medical','dentist','doctor','health']),
        ('Utilities & telecom', ['utilit','telecom','telephone','cable','internet']),
        ('Travel & transport', ['hotel','motel','airline','taxi','rail','transport','air carrier','travel']),
        ('Retail & shopping', ['store','clothing','department','furniture','shoe','sporting','jewelry','hardware']),
        ('Leisure & entertainment', ['amusement','motion picture','theater','recreation','entertainment']),
    ]
    return next((g for g,keys in groups if any(k in s for k in keys)), 'Other services')

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (ROOT/'reports').mkdir(exist_ok=True)
    source = {n: read_csv(n) for n in ['users','cards','transactions','mcc_codes']}
    checks = []
    def check(name, observed, expected=0, severity='ERROR'):
        ok = observed == expected
        checks.append(dict(check=name, observed=observed, expected=expected, status='PASS' if ok else severity))
        if not ok and severity == 'ERROR': raise ValueError(f'{name}: {observed} != {expected}')
    for name, rows in source.items():
        key = 'mcc_id' if name=='mcc_codes' else 'id'
        check(name+'_duplicate_key',len(rows)-len({r[key] for r in rows}))
    users = {int(r['id']):r for r in source['users']}
    cards = {int(r['id']):r for r in source['cards']}
    mccs = {int(r['mcc_id']):r for r in source['mcc_codes']}
    states = set('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC'.split())
    tx = []
    violations = Counter()
    for r in source['transactions']:
        cid, card, mcc = int(r['client_id']),int(r['card_id']),int(r['mcc'])
        violations['orphan_customer'] += cid not in users
        violations['orphan_card'] += card not in cards
        violations['orphan_mcc'] += mcc not in mccs
        violations['owner_mismatch'] += card in cards and int(cards[card]['client_id']) != cid
        dt = datetime.fromisoformat(r['date'])
        errors = [e.strip() for e in r.get('errors','').split(',') if e.strip()]
        amt = money(r['amount']); city = r['merchant_city'].strip()
        physical = city.upper() != 'ONLINE'
        state = r['merchant_state'].strip()
        tx.append(dict(TransactionID=int(r['id']),Timestamp=dt.isoformat(sep=' '),Date=dt.date().isoformat(),
            ClientID=cid,CardID=card,AmountCents=amt,Amount=f'{amt/100:.2f}',
            Channel=r['use_chip'].replace(' Transaction',''),MerchantID=int(r['merchant_id']),
            MerchantCity=city,MerchantState=state or ('Online / not provided' if not physical else 'Not provided'),
            MCC=mcc,Errors='; '.join(errors),HasError=int(bool(errors)),ErrorCount=len(errors),
            PrimaryError=errors[0] if errors else 'No error',
            AmountType='Positive' if amt>0 else 'Negative (refund-like)' if amt<0 else 'Zero',
            IsPhysicalUS=int(physical and state in states)))
    for n in ['orphan_customer','orphan_card','orphan_mcc','owner_mismatch']: check(n,violations[n])
    check('card_orphan_customer',sum(int(c['client_id']) not in users for c in cards.values()))
    tx.sort(key=lambda r:(r['Timestamp'],r['TransactionID']))
    start=date.fromisoformat(tx[0]['Date']); end=date.fromisoformat(tx[-1]['Date'])
    positive=defaultdict(list); carddays=defaultdict(set)
    for t in tx:
        if t['AmountCents']>0 and not t['HasError']: positive[t['MCC']].append(t['AmountCents'])
        if t['IsPhysicalUS']: carddays[(t['CardID'],t['Date'])].add(t['MerchantState'])
    thresholds={m: quantile(a,0.99) for m,a in positive.items() if len(a)>=30}
    error_windows=defaultdict(deque); activity=defaultdict(list); bridge=[]
    for t in tx:
        card=t['CardID']; dt=datetime.fromisoformat(t['Timestamp']); window=error_windows[card]
        while window and dt-window[0]>timedelta(minutes=60): window.popleft()
        if t['HasError']: window.append(dt)
        t['HighValueFlag']=int(t['AmountCents']>0 and not t['HasError'] and t['MCC'] in thresholds and t['AmountCents']>thresholds[t['MCC']])
        t['MultiStateFlag']=int(t['IsPhysicalUS'] and len(carddays[(card,t['Date'])])>=2)
        t['ErrorBurstFlag']=int(t['HasError'] and len(window)>=3)
        t['ReviewFlag']=int(any(t[k] for k in ['HighValueFlag','MultiStateFlag','ErrorBurstFlag']))
        t['ReviewStatus']='Review' if t['ReviewFlag'] else 'Unflagged'
        t['ReviewReason']=' | '.join(n for k,n in [('HighValueFlag','MCC > P99'),('MultiStateFlag','Multi-state card-day'),('ErrorBurstFlag','3+ errors / 60 min')] if t[k]) or 'None'
        activity[card].append(t)
        for e in t['Errors'].split('; '):
            if e: bridge.append(dict(TransactionID=t['TransactionID'],Error=e))
    dimusers=[]
    for uid,r in users.items():
        age=int(r['current_age']); score=int(r['credit_score'])
        dimusers.append(dict(ClientID=uid,SnapshotAge=age,AgeBand='Under 30' if age<30 else '30–44' if age<45 else '45–59' if age<60 else '60+',
            Gender=r['gender'],YearlyIncome=f'{money(r["yearly_income"])/100:.2f}',TotalDebt=f'{money(r["total_debt"])/100:.2f}',CreditScore=score,
            CreditBand='<580' if score<580 else '580–669' if score<670 else '670–739' if score<740 else '740–799' if score<800 else '800+',
            ReportedCreditCards=int(r['num_credit_cards'])))
    dimcards=[]
    for card,r in cards.items():
        a=activity[card]; opened=date.fromisoformat(r['acct_open_date'][:10]); last=a[-1]['Date'] if a else ''
        dimcards.append(dict(CardID=card,ClientID=int(r['client_id']),Brand=r['card_brand'],CardType=r['card_type'],HasChip=r['has_chip'],
            CreditLimit=f'{money(r["credit_limit"])/100:.2f}',OpenedDate=opened.isoformat(),Expires=r['expires'],
            ObservedTransactions=len(a),ObservedActive=int(bool(a)),LastObservedDate=last,
            DaysSinceObserved=(end-date.fromisoformat(last)).days if last else '',
            SnapshotStatus='Seen in last 30d' if last and date.fromisoformat(last)>=end-timedelta(days=29) else 'Seen earlier' if last else 'No observed activity',
            LongOpenUnobserved=int(not a and opened<=end-timedelta(days=730))))
    dates=[]
    # Full calendar years for time intelligence. Coverage measures use MAX(Fact[Date]), not MAX(calendar).
    day=date(start.year,1,1)
    while day<=date(end.year,12,31):
        dates.append(dict(Date=day.isoformat(),Year=day.year,MonthNumber=day.month,Month=day.strftime('%b'),YearMonth=day.strftime('%Y-%m'),MonthStart=day.replace(day=1).isoformat(),Weekday=day.strftime('%a')))
        day+=timedelta(days=1)
    tables=dict(DimCustomer=dimusers,DimCard=dimcards,DimDate=dates,
        DimMCC=[dict(MCC=m,Description=r['description'],MerchantGroup=merchant_group(r['description']),P99Amount=f'{thresholds[m]/100:.4f}' if m in thresholds else '',ReferenceCount=len(positive[m])) for m,r in mccs.items()],
        FactTransaction=tx,FactError=bridge,
        DimRule=[dict(Rule=n) for n in ['MCC > P99','Multi-state card-day','3+ errors / 60 min']])
    db=ROOT/'data/analytics.sqlite'
    if db.exists(): db.unlink()
    con=sqlite3.connect(db)
    integer={'TransactionID','ClientID','CardID','MerchantID','MCC','AmountCents','HasError','ErrorCount','IsPhysicalUS','HighValueFlag','MultiStateFlag','ErrorBurstFlag','ReviewFlag','SnapshotAge','CreditScore','ReportedCreditCards','ObservedTransactions','ObservedActive','DaysSinceObserved','LongOpenUnobserved','Year','MonthNumber','ReferenceCount'}
    real={'Amount','YearlyIncome','TotalDebt','CreditLimit','P99Amount'}
    for name,rows in tables.items():
        write_csv(name,rows); cols=list(rows[0])
        spec=','.join('"'+c+'" '+('INTEGER' if c in integer else 'REAL' if c in real else 'TEXT') for c in cols)
        con.execute(f'CREATE TABLE "{name}" ({spec})')
        vals=[[None if r[c]=='' else r[c] for c in cols] for r in rows]
        con.executemany(f'INSERT INTO "{name}" VALUES ({",".join("?" for _ in cols)})',vals)
    for col in ['TransactionID','CardID','ClientID','Date','MCC']: con.execute(f'CREATE INDEX idx_tx_{col} ON FactTransaction({col})')
    con.executescript('''
    CREATE VIEW v_transactions AS
    SELECT t.*, c.Brand,c.CardType,c.CreditLimit,u.AgeBand,u.CreditBand,u.CreditScore,u.YearlyIncome,m.Description,m.MerchantGroup
    FROM FactTransaction t JOIN DimCard c USING(CardID) JOIN DimCustomer u ON c.ClientID=u.ClientID JOIN DimMCC m USING(MCC);
    CREATE VIEW v_monthly AS
    SELECT substr(Date,1,7) AS Month,COUNT(*) Attempts,SUM(HasError) ErrorAttempts,
      SUM(CASE WHEN HasError=0 AND AmountCents>0 THEN AmountCents ELSE 0 END) PositiveCents,
      SUM(CASE WHEN HasError=0 THEN AmountCents ELSE 0 END) NetCents,
      COUNT(DISTINCT ClientID) ActiveCustomers,SUM(ReviewFlag) ReviewAttempts
    FROM FactTransaction GROUP BY substr(Date,1,7);
    ''')
    con.commit()
    (ROOT/'sql').mkdir(exist_ok=True)
    schema='-- Generated SQLite DDL. Run on an empty database; data loading is handled by scripts/pipeline.py.\n\n'
    schema+='\n\n'.join(r[0]+';' for r in con.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY CASE type WHEN 'table' THEN 1 WHEN 'index' THEN 2 ELSE 3 END,name"))+'\n'
    (ROOT/'sql/schema.sql').write_text(schema,encoding='utf-8')
    monthly=[dict(zip([c[0] for c in cur.description], row)) for cur in [con.execute('SELECT * FROM v_monthly ORDER BY Month')] for row in cur]
    def scalar(q): return con.execute(q).fetchone()[0]
    metrics=dict(rows={k:len(v) for k,v in source.items()},start=start.isoformat(),end=end.isoformat(),
        attempts=len(tx),error_attempts=sum(t['HasError'] for t in tx),multi_error_attempts=sum(t['ErrorCount']>1 for t in tx),error_mentions=len(bridge),
        positive_cents=sum(t['AmountCents'] for t in tx if not t['HasError'] and t['AmountCents']>0),
        negative_cents=sum(t['AmountCents'] for t in tx if not t['HasError'] and t['AmountCents']<0),
        net_cents=sum(t['AmountCents'] for t in tx if not t['HasError']),all_recorded_cents=sum(t['AmountCents'] for t in tx),
        negative_attempts=sum(t['AmountCents']<0 for t in tx),zero_attempts=sum(t['AmountCents']==0 for t in tx),
        active_customers=len({t['ClientID'] for t in tx}),active_cards=len({t['CardID'] for t in tx}),
        card_count=len(cards),customer_count=len(users),
        review_attempts=sum(t['ReviewFlag'] for t in tx),high_value=sum(t['HighValueFlag'] for t in tx),multi_state=sum(t['MultiStateFlag'] for t in tx),error_burst=sum(t['ErrorBurstFlag'] for t in tx),
        last30_active_cards=scalar("SELECT COUNT(DISTINCT CardID) FROM FactTransaction WHERE Date>=date((SELECT MAX(Date) FROM FactTransaction),'-29 days')"),
        missing_state=sum(not r['merchant_state'].strip() for r in source['transactions']),
        missing_zip=sum(not r['zip'].strip() for r in source['transactions']))
    check('net_reconciles',metrics['net_cents'],metrics['positive_cents']+metrics['negative_cents'])
    check('monthly_attempts_reconcile',sum(r['Attempts'] for r in monthly),len(tx))
    check('monthly_positive_reconcile',sum(r['PositiveCents'] for r in monthly),metrics['positive_cents'])
    check('error_mentions_reconcile',len(bridge),sum(t['ErrorCount'] for t in tx))
    check('snapshot_card_count',sum(c['ObservedActive'] for c in dimcards),metrics['active_cards'])
    check('review_union_bound',int(metrics['review_attempts']<=metrics['high_value']+metrics['multi_state']+metrics['error_burst']),1)
    dq=dict(checks=checks,profile=dict(missing_state=metrics['missing_state'],missing_zip=metrics['missing_zip'],blank_errors_means='No recorded error; not confirmed settlement',
        age_note='Snapshot age is retained; it is not age at transaction date.',coverage_note='Only customers/cards with rows in this export are observed. No activity is not proven dormancy.',
        currency_note='USD assumed from US dataset context; no currency column exists.'),source_sha256={n:hashlib.sha256((RAW/(n+'.csv')).read_bytes()).hexdigest() for n in source})
    (ROOT/'reports/data_quality.json').write_text(json.dumps(dq,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'reports/metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    write_csv('MonthlySummary',monthly)
    print(json.dumps(metrics,indent=2))
    con.close()
    return metrics

if __name__=='__main__': main()
