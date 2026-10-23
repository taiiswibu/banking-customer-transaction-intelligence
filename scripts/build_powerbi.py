"""Generate a native Power BI PBIP/TMDL/PBIR project, with data-bound visuals."""
from __future__ import annotations
import csv,json,hashlib,re,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PBI=ROOT/'powerbi'; MODEL=PBI/'Banking.SemanticModel'; REPORT=PBI/'Banking.Report'
SCHEMA='https://developer.microsoft.com/json-schemas/fabric/item/'
NAVY='#10243A'; TEAL='#008C95'; BG='#F2F5F9'; MUTED='#5D7186'; INK='#172D45'

def dump(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

def uid(s):return hashlib.sha256(s.encode()).hexdigest()[:20]
def lit(x):return {'expr':{'Literal':{'Value':x}}}
def color(s):return {'solid':{'color':lit("'"+s+"'")}}
def obj(**props):return [{'properties':props}]
def qname(s):return "'"+s.replace("'","''")+"'"

# Explicit semantic types. Unlisted columns are text, never implicitly summarized IDs.
INT=set('TransactionID ClientID CardID MerchantID MCC AmountCents HasError ErrorCount IsPhysicalUS HighValueFlag MultiStateFlag ErrorBurstFlag ReviewFlag SnapshotAge CreditScore ReportedCreditCards ObservedTransactions ObservedActive DaysSinceObserved LongOpenUnobserved Year MonthNumber ReferenceCount'.split())
MONEY=set('Amount YearlyIncome TotalDebt CreditLimit P99Amount'.split())
DATES=set('Date MonthStart OpenedDate Expires LastObservedDate Timestamp'.split())

MEASURES={
 'Attempts':('COUNTROWS(FactTransaction)','#,0','Activity'),
 'Error Attempts':('COALESCE(SUM(FactTransaction[HasError]), 0)','#,0','Payment'),
 'Error Rate':('DIVIDE([Error Attempts], [Attempts])','0.00%','Payment'),
 'No Recorded Error Attempts':('[Attempts] - [Error Attempts]','#,0','Payment'),
 'Positive Volume':('CALCULATE(SUM(FactTransaction[Amount]), KEEPFILTERS(FactTransaction[HasError] = 0), KEEPFILTERS(FactTransaction[Amount] > 0))','$#,0.00;($#,0.00)','Volume'),
 'Negative Volume':('CALCULATE(SUM(FactTransaction[Amount]), KEEPFILTERS(FactTransaction[HasError] = 0), KEEPFILTERS(FactTransaction[Amount] < 0))','$#,0.00;($#,0.00)','Volume'),
 'Net Volume':('CALCULATE(SUM(FactTransaction[Amount]), KEEPFILTERS(FactTransaction[HasError] = 0))','$#,0.00;($#,0.00)','Volume'),
 'All Recorded Volume':('SUM(FactTransaction[Amount])','$#,0.00;($#,0.00)','Volume'),
 'Error Row Volume':('CALCULATE(SUM(FactTransaction[Amount]), KEEPFILTERS(FactTransaction[HasError] = 1))','$#,0.00;($#,0.00)','Volume'),
 'Average Positive Amount':('DIVIDE([Positive Volume], CALCULATE([Attempts], KEEPFILTERS(FactTransaction[HasError] = 0), KEEPFILTERS(FactTransaction[Amount] > 0)))','$#,0.00','Volume'),
 'Observed Customers':('DISTINCTCOUNT(FactTransaction[ClientID])','#,0','Activity'),
 'Observed Cards':('DISTINCTCOUNT(FactTransaction[CardID])','#,0','Activity'),
 'Portfolio Cards':('COUNTROWS(DimCard)','#,0','Portfolio'),
 'Portfolio Customers':('COUNTROWS(DimCustomer)','#,0','Portfolio'),
 'Observed Card Coverage':('DIVIDE([Observed Cards], [Portfolio Cards])','0.00%','Portfolio'),
 'Snapshot Unobserved Cards':('CALCULATE(COUNTROWS(DimCard), KEEPFILTERS(DimCard[ObservedActive] = 0))','#,0','Snapshot'),
 'Snapshot Recent Cards':('CALCULATE(COUNTROWS(DimCard), KEEPFILTERS(DimCard[SnapshotStatus] = "Seen in last 30d"))','#,0','Snapshot'),
 'Snapshot Long Open Unobserved':('CALCULATE(COUNTROWS(DimCard), KEEPFILTERS(DimCard[LongOpenUnobserved] = 1))','#,0','Snapshot'),
 'Snapshot As Of':('CALCULATE(MAX(FactTransaction[Date]), REMOVEFILTERS())','yyyy-MM-dd','Snapshot'),
 'Snapshot Recent Observed Cards':('VAR EndDate = [Snapshot As Of]\nRETURN CALCULATE([Observed Cards], REMOVEFILTERS(DimDate), DATESBETWEEN(DimDate[Date], EndDate - 29, EndDate))','#,0','Snapshot'),
 'Review Attempts':('COALESCE(SUM(FactTransaction[ReviewFlag]), 0)','#,0','Review'),
 'Review Rate':('DIVIDE([Review Attempts], [Attempts])','0.00%','Review'),
 'High Value Attempts':('COALESCE(SUM(FactTransaction[HighValueFlag]), 0)','#,0','Review'),
 'Multi State Attempts':('COALESCE(SUM(FactTransaction[MultiStateFlag]), 0)','#,0','Review'),
 'Error Burst Attempts':('COALESCE(SUM(FactTransaction[ErrorBurstFlag]), 0)','#,0','Review'),
 'Rule Attempts':('SWITCH(SELECTEDVALUE(DimRule[Rule]), "MCC > P99", [High Value Attempts], "Multi-state card-day", [Multi State Attempts], "3+ errors / 60 min", [Error Burst Attempts])','#,0','Review'),
 'Error Mentions':('COUNTROWS(FactError)','#,0','Payment'),
 'Multi Error Attempts':('CALCULATE([Attempts], KEEPFILTERS(FactTransaction[ErrorCount] > 1))','#,0','Payment'),
 'Technical Error Attempts':('CALCULATE([Attempts], FILTER(FactTransaction, CONTAINSSTRING(FactTransaction[Errors], "Technical Glitch")))','#,0','Payment'),
 'Primary Error Attempts':('CALCULATE([Attempts], KEEPFILTERS(FactTransaction[HasError] = 1))','#,0','Payment'),
 'Positive Volume PY':('CALCULATE([Positive Volume], SAMEPERIODLASTYEAR(DimDate[Date]))','$#,0.00','Time intelligence'),
 'Positive Volume YoY':('DIVIDE([Positive Volume] - [Positive Volume PY], [Positive Volume PY])','0.00%','Time intelligence'),
 'Positive Volume Running':('CALCULATE([Positive Volume], FILTER(ALLSELECTED(DimDate), DimDate[Date] <= MAX(DimDate[Date])))','$#,0.00','Time intelligence'),
 'Positive Volume Last 30d':('VAR EndDate = MAX(FactTransaction[Date])\nRETURN CALCULATE([Positive Volume], REMOVEFILTERS(DimDate), DATESBETWEEN(DimDate[Date], EndDate - 29, EndDate))','$#,0.00','Time intelligence'),
 'Credit Volume Last 30d':('CALCULATE([Positive Volume Last 30d], KEEPFILTERS(DimCard[CardType] = "Credit"))','$#,0.00','Proxy'),
 'Credit Limit Snapshot':('CALCULATE(SUM(DimCard[CreditLimit]), KEEPFILTERS(DimCard[CardType] = "Credit"))','$#,0.00','Proxy'),
 'Volume To Limit Proxy':('DIVIDE([Credit Volume Last 30d], [Credit Limit Snapshot])','0.00%','Proxy'),
 'Volume Reconciliation Delta':('[Net Volume] - COALESCE([Positive Volume], 0) - COALESCE([Negative Volume], 0)','$#,0.00','Validation'),
 'Error Volume Reconciliation Delta':('[All Recorded Volume] - COALESCE([Net Volume], 0) - COALESCE([Error Row Volume], 0)','$#,0.00','Validation'),
}

def build_model(data_folder=None):
    definition=MODEL/'definition';(definition/'tables').mkdir(parents=True,exist_ok=True)
    folder=str(data_folder or ROOT/'data/processed').replace('\\','/').replace('"','""')
    dump(MODEL/'definition.pbism',{'$schema':SCHEMA+'semanticModel/definitionProperties/1.0.0/schema.json','version':'4.0','settings':{}})
    (definition/'database.tmdl').write_text('database BankingIntelligence\n\tcompatibilityLevel: 1601\n\tcompatibilityMode: powerBI\n',encoding='utf-8')
    names=['DimCustomer','DimCard','DimDate','DimMCC','FactTransaction','FactError','DimRule']
    model='model Model\n\tculture: en-US\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\tdiscourageImplicitMeasures\n\tsourceQueryCulture: en-US\n\tdataAccessOptions\n\t\tlegacyRedirects\n\t\treturnErrorValuesAsNull\n\nannotation __PBI_TimeIntelligenceEnabled = 0\n\n'
    model+='\n'.join('ref table '+n for n in names)+'\nref table KPI_Measures\n'
    (definition/'model.tmdl').write_text(model,encoding='utf-8')
    (definition/'expressions.tmdl').write_text('expression DataFolder = "'+folder+'"\n\tannotation PBI_ResultType = Text\n',encoding='utf-8')
    metadata={}
    for name in names:
        with (ROOT/'data/processed'/(name+'.csv')).open(encoding='utf-8',newline='') as f: cols=next(csv.reader(f))
        metadata[name]=cols
        text='table '+name+'\n'
        if name=='DimDate':text+='\tdataCategory: Time\n'
        for c in cols:
            typ='int64' if c in INT else 'decimal' if c in MONEY else 'dateTime' if c in DATES else 'string'
            text+='\n\tcolumn '+qname(c)+'\n\t\tdataType: '+typ+'\n\t\tsourceColumn: '+c+'\n\t\tsummarizeBy: none\n'
            if c in MONEY:text+='\t\tformatString: #,0.00\n'
            if c in DATES:text+='\t\tformatString: '+('yyyy-MM-dd HH:mm' if c=='Timestamp' else 'yyyy-MM-dd')+'\n'
            if (c in INT and c.endswith('ID')) or c in ['AmountCents','IsPhysicalUS','HighValueFlag','MultiStateFlag','ErrorBurstFlag','ReviewFlag','HasError','LongOpenUnobserved','ObservedActive']:text+='\t\tisHidden\n'
            if name=='DimDate' and c=='Date':text+='\t\tisKey\n\t\tannotation UnderlyingDateTimeDataType = Date\n'
            if name=='DimDate' and c=='Month':text+='\t\tsortByColumn: MonthNumber\n'
        transforms=[]
        for c in cols:
            t='Int64.Type' if c in INT else 'Currency.Type' if c in MONEY else 'type datetime' if c=='Timestamp' else 'type date' if c in DATES else 'type text'
            transforms.append('{"'+c+'", '+t+'}')
        # CSV empty numeric/date values become null explicitly before casting.
        nullable=[c for c in cols if c in INT|MONEY|DATES]
        m='let\n  Source = Csv.Document(File.Contents(DataFolder & "/'+name+'.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),\n  Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),\n  Nulls = Table.ReplaceValue(Headers, "", null, Replacer.ReplaceValue, {'+','.join('"'+c+'"' for c in nullable)+'}),\n  Typed = Table.TransformColumnTypes(Nulls, {'+', '.join(transforms)+'}, "en-US")\nin\n  Typed'
        text+='\n\tpartition '+name+' = m\n\t\tmode: import\n\t\tsource =\n'+'\n'.join('\t\t\t'+l for l in m.splitlines())+'\n'
        (definition/'tables'/(name+'.tmdl')).write_text(text,encoding='utf-8')
    obsolete=definition/'tables/Measures.tmdl'
    if obsolete.exists(): obsolete.unlink()
    text='table KPI_Measures\n'
    for name,(dax,fmt,group) in MEASURES.items():
        text+='\n\tmeasure '+qname(name)+' =\n'+'\n'.join('\t\t\t'+l for l in dax.splitlines())+'\n\t\tformatString: '+fmt+'\n\t\tdisplayFolder: '+group+'\n'
    text+='\n\tcolumn Anchor\n\t\tdataType: int64\n\t\tisHidden\n\t\tsourceColumn: Anchor\n\t\tsummarizeBy: none\n\n\tpartition KPI_Measures = m\n\t\tmode: import\n\t\tsource = #table(type table [Anchor = Int64.Type], {{0}})\n'
    (definition/'tables/KPI_Measures.tmdl').write_text(text,encoding='utf-8')
    rel=[('DimCard','ClientID','DimCustomer','ClientID'),('FactTransaction','CardID','DimCard','CardID'),('FactTransaction','Date','DimDate','Date'),('FactTransaction','MCC','DimMCC','MCC'),('FactError','TransactionID','FactTransaction','TransactionID')]
    relationships=''
    for f,fc,t,tc in rel:
        relationships+='relationship '+uid(f+fc+t+tc)+'\n\tfromColumn: '+f+'.'+fc+'\n\ttoColumn: '+t+'.'+tc+'\n\tfromCardinality: many\n\ttoCardinality: one\n\tcrossFilteringBehavior: oneDirection\n\n'
    (definition/'relationships.tmdl').write_text(relationships,encoding='utf-8')
    dump(ROOT/'reports/model_manifest.json',{'tables':metadata,'measures':list(MEASURES),'relationships':rel,'data_folder':folder})
    # A standalone human-readable DAX catalog, not a second source of truth.
    (ROOT/'docs/DAX_CATALOG.md').write_text('# DAX measures\n\nGenerated from scripts/build_powerbi.py. Model culture: en-US.\n\n'+'\n\n'.join('## '+n+'\n\n```dax\n'+n+' = '+d+'\n```\n\nFolder: '+g+'; format: `'+f+'`.' for n,(d,f,g) in MEASURES.items())+'\n',encoding='utf-8')

def field(table,col,measure=False):
    return {'field':{('Measure' if measure else 'Column'):{'Expression':{'SourceRef':{'Entity':table}},'Property':col}},'queryRef':table+'.'+col,'nativeQueryRef':col}

def visual(name,typ,box,title='',query=None,objects=None,background='#FFFFFF'):
    x,y,w,h=box
    v={'$schema':SCHEMA+'report/definition/visualContainer/2.7.0/schema.json','name':uid(name),'position':dict(x=x,y=y,z=1000,height=h,width=w,tabOrder=0),
       'visual':{'visualType':typ,'drillFilterOtherVisuals':True}}
    if query:v['visual']['query']={'queryState':query}
    v['visual']['objects']=objects or {}
    container={'background':obj(show=lit('true'),color=color(background),transparency=lit('0D')),
        'border':obj(show=lit('true'),color=color('#E3E9F0'),radius=lit('10D')),
        'visualHeader':obj(show=lit('false'))}
    if title:container['title']=obj(show=lit('true'),text=lit(qname(title)),fontColor=color(INK),fontSize=lit('11D'),alignment=lit("'left'"),fontFamily=lit("'Segoe UI Semibold'"))
    v['visual']['visualContainerObjects']=container
    return v

def text(name,s,box,size=14,fg=INK,bg=BG):
    o={'general':obj(paragraphs=[{'textRuns':[{'value':s,'textStyle':{'fontFamily':'Segoe UI','fontSize':str(size)+'px','color':fg}}]}])}
    v=visual(name,'textbox',box,objects=o,background=bg)
    v['visual']['visualContainerObjects']['border']=obj(show=lit('false'))
    return v

def card(name,measure,box,label=None):
    # Classic card avoids depending on June 2026 new-card layout defaults.
    o={'labels':obj(color=color(INK),fontSize=lit('25D'),labelDisplayUnits=lit('0D')),
       'categoryLabels':obj(show=lit('false'))}
    return visual(name,'card',box,label or measure,{'Values':{'projections':[field('KPI_Measures',measure,True)]}},o)

def chart(name,typ,box,title,table,col,measure):
    o={'categoryAxis':obj(fontSize=lit('9D'),fontColor=color(MUTED),showAxisTitle=lit('false')),
       'valueAxis':obj(fontSize=lit('9D'),fontColor=color(MUTED),showAxisTitle=lit('false'),gridlineColor=color('#E8EDF2')),
       'dataPoint':obj(defaultColor=color(TEAL))}
    v=visual(name,typ,box,title,{'Category':{'projections':[field(table,col)]},'Y':{'projections':[field('KPI_Measures',measure,True)]}},o)
    # Explicit ascending order for calendar charts.
    if table=='DimDate':
        v['visual']['query']['sortDefinition']={'sort':[{'field':field(table,col)['field'],'direction':'Ascending'}]}
    return v

def slicer(name,box,table,col,title):
    return visual(name,'slicer',box,title,{'Values':{'projections':[field(table,col)]}},
        {'data':obj(mode=lit("'Dropdown'")),'header':obj(show=lit('false'))})

def table(name,box,title,fields):
    p=[field(t,c,m) for t,c,m in fields]
    return visual(name,'tableEx',box,title,{'Values':{'projections':p}},
        {'columnHeaders':obj(fontSize=lit('10D'),fontColor=color('#FFFFFF'),backColor=color(NAVY)),
         'values':obj(fontSize=lit('10D'),backColor=color('#FFFFFF'),backColorAlternate=color('#F3F7FA')),
         'grid':obj(gridVertical=lit('false'),rowPadding=lit('6D'))})

def build_report():
    definition=REPORT/'definition'
    if definition.exists():shutil.rmtree(definition)
    dump(PBI/'Banking.pbip',{'version':'1.0','artifacts':[{'report':{'path':'Banking.Report'}}],'settings':{'enableAutoRecovery':True}})
    dump(REPORT/'definition.pbir',{'$schema':SCHEMA+'report/definitionProperties/2.0.0/schema.json','version':'4.0','datasetReference':{'byPath':{'path':'../Banking.SemanticModel'}}})
    dump(definition/'version.json',{'$schema':SCHEMA+'report/definition/versionMetadata/1.0.0/schema.json','version':'2.0.0'})
    theme={'name':'BankingNavyTeal','dataColors':[TEAL,'#386EAC','#E3A347','#B0667B','#568E78','#6D78AE','#72B8BA'],
        'background':'#FFFFFF','foreground':INK,'tableAccent':TEAL,
        'textClasses':{'label':{'fontFace':'Segoe UI','fontSize':10,'color':MUTED},'title':{'fontFace':'Segoe UI Semibold','fontSize':12,'color':INK},'callout':{'fontFace':'Segoe UI Semibold','fontSize':26,'color':INK}}}
    dump(REPORT/'StaticResources/RegisteredResources/BankingNavyTeal.json',theme)
    dump(definition/'report.json',{'$schema':SCHEMA+'report/definition/report/3.0.0/schema.json',
        'themeCollection':{'baseTheme':{'name':'CY24SU10','reportVersionAtImport':{'visual':'1.8.0','page':'1.3.0','report':'2.0.0'},'type':'SharedResources'},
        'customTheme':{'name':'BankingNavyTeal','reportVersionAtImport':{'visual':'1.8.0','page':'1.3.0','report':'2.0.0'},'type':'RegisteredResources'}},
        'resourcePackages':[{'name':'RegisteredResources','type':'RegisteredResources','items':[{'name':'BankingNavyTeal','path':'BankingNavyTeal.json','type':'CustomTheme'}]}]})
    specs=[
      ('01_overview','01  Executive overview','Transaction intelligence','Portfolio performance · observed export, Jan 2022–Oct 2024',
       [('Positive Volume','Positive volume · no errors'),('Net Volume','Net volume · no errors'),('Attempts','Recorded attempts'),('Error Rate','Recorded error rate'),('Observed Customers','Observed customers')]),
      ('02_portfolio','02  Customers & cards','Customers & card portfolio','Coverage first · snapshot statuses are fixed at 31 Oct 2024',
       [('Portfolio Cards','Cards in snapshot'),('Observed Cards','Cards seen · selection'),('Snapshot Unobserved Cards','Cards never seen · export'),('Observed Card Coverage','Observed card coverage'),('Snapshot Recent Cards','Seen in last 30d · snapshot')]),
      ('03_payment','03  Payment performance','Payment performance','Recorded errors · blank error text does not confirm settlement',
       [('Error Attempts','Attempts with errors'),('Error Rate','Recorded error rate'),('Error Mentions','Error mentions'),('Multi Error Attempts','Multi-error attempts'),('Technical Error Attempts','Technical error attempts')]),
      ('04_review','04  Transaction review','Transaction review desk','Rule-based prioritization · review flags are not fraud labels',
       [('Review Attempts','Flagged attempts'),('Review Rate','Share of all attempts'),('High Value Attempts','MCC > P99'),('Multi State Attempts','Multi-state attempts'),('Error Burst Attempts','3+ errors / 60 min')]),
    ]
    pageids=[uid(s[0]) for s in specs]
    dump(definition/'pages/pages.json',{'$schema':SCHEMA+'report/definition/pagesMetadata/1.0.0/schema.json','pageOrder':pageids,'activePageName':pageids[0]})
    total=0
    for idx,(key,display,title,subtitle,kpis) in enumerate(specs):
        pid=pageids[idx]; d=definition/'pages'/pid
        dump(d/'page.json',{'$schema':SCHEMA+'report/definition/page/2.1.0/schema.json','name':pid,'displayName':display,'displayOption':'FitToPage','height':900,'width':1440,
            'objects':{'background':obj(color=color(BG),transparency=lit('0D'))}})
        header=text(key+'header','',(0,0,1440,114),12,'#FFFFFF',NAVY)
        header['position']['z']=0
        vs=[header,text(key+'brand','XÓM BANK  /  ANALYTICS STUDIO',(24,14,890,27),13,'#72D2D0',NAVY),
            text(key+'title',title,(24,42,900,42),28,'#FFFFFF',NAVY),text(key+'sub',subtitle,(24,88,950,26),12,'#B4C8D8',NAVY),
            text(key+'foot','SOURCE  Xóm Data export  |  USD assumed  |  No recorded error ≠ confirmed settlement  |  Code-first PBIR + TMDL',(24,862,1392,25),11,MUTED),
            slicer(key+'year',(1008,18,196,72),'DimDate','Year','Year'),slicer(key+'channel',(1216,18,200,72),'FactTransaction','Channel','Channel')]
        # Native page navigator supplies working navigation without per-button setup.
        vs.append(visual(key+'nav','pageNavigator',(24,120,1392,40),objects={'text':obj(fontSize=lit('10D'),fontColor=color(INK))}))
        for i,(measure,label) in enumerate(kpis):vs.append(card(key+'kpi'+str(i),measure,(24+i*282,178,264,108),label))
        if idx==0:
            vs.extend([
                chart('monthly_volume','lineChart',(24,306,900,292),'Monthly positive volume · no recorded errors','DimDate','YearMonth','Positive Volume'),
                chart('channel_volume','clusteredColumnChart',(944,306,472,292),'Positive volume by channel','FactTransaction','Channel','Positive Volume'),
                chart('category_volume','clusteredBarChart',(24,618,900,224),'Positive volume by merchant group','DimMCC','MerchantGroup','Positive Volume'),
                text('overview_note','READ THE KPI\n\nPositive volume includes transfers.\nNet volume includes negative rows.\nAmounts on error rows are excluded.\n2024 covers January–October only.',(944,618,472,224),16,INK,'#E1F1F1')])
        elif idx==1:
            vs.extend([
                chart('cards_type','clusteredBarChart',(24,306,666,280),'Snapshot cards by type','DimCard','CardType','Portfolio Cards'),
                chart('credit_band','clusteredColumnChart',(710,306,706,280),'Positive volume by customer credit band','DimCustomer','CreditBand','Positive Volume'),
                table('status_table',(24,606,666,236),'Observed card status · snapshot',[('DimCard','SnapshotStatus',False),('KPI_Measures','Portfolio Cards',True)]),
                chart('age_volume','clusteredBarChart',(710,606,706,236),'Positive volume by snapshot age band','DimCustomer','AgeBand','Positive Volume')])
        elif idx==2:
            vs.extend([
                chart('error_month','lineChart',(24,306,900,280),'Recorded error rate by month','DimDate','YearMonth','Error Rate'),
                chart('error_channel','clusteredColumnChart',(944,306,472,280),'Recorded error rate by channel','FactTransaction','Channel','Error Rate'),
                chart('error_primary','clusteredBarChart',(24,606,900,236),'Primary error · each affected attempt counted once','FactTransaction','PrimaryError','Primary Error Attempts'),
                table('mentions',(944,606,472,236),'Error mentions · categories may overlap',[('FactError','Error',False),('KPI_Measures','Error Mentions',True)])])
        else:
            vs.extend([
                chart('review_month','lineChart',(24,306,900,250),'Flagged attempts by month','DimDate','YearMonth','Review Attempts'),
                chart('review_rules','clusteredBarChart',(944,306,472,250),'Rule counts · overlap allowed','DimRule','Rule','Rule Attempts'),
                slicer('review_reason',(1190,580,226,65),'FactTransaction','ReviewReason','Review reason'),
                table('review_queue',(24,580,1146,262),'Review queue · flagged rows only',[
                    ('FactTransaction','TransactionID',False),('FactTransaction','Timestamp',False),('DimCard','CardID',False),
                    ('FactTransaction','Amount',False),('FactTransaction','MerchantState',False),('FactTransaction','ReviewReason',False)]),
                text('review_note','P99 is fitted on the full export.\nMulti-state uses calendar days.\nBurst is a rolling 60-minute rule.\nCounts are descriptive, not validated detection.',(1190,662,226,180),12,MUTED)])
            # The detail table defaults to Review via a categorical visual filter.
            v=next(v for v in vs if v['name']==uid('review_queue'))
            v['filterConfig']={'filters':[{'name':uid('default_review_filter'),'field':field('FactTransaction','ReviewStatus')['field'],
                'type':'Categorical','filter':{'Version':2,'From':[{'Name':'t','Entity':'FactTransaction','Type':0}],
                'Where':[{'Condition':{'In':{'Expressions':[{'Column':{'Expression':{'SourceRef':{'Source':'t'}},'Property':'ReviewStatus'}}],
                    'Values':[[{'Literal':{'Value':"'Review'"}}]]}}}]}}]}
        for order,v in enumerate(vs):
            v['position']['tabOrder']=order
            dump(d/'visuals'/v['name']/'visual.json',v)
        total+=len(vs)
    print(f'Generated native Power BI project: 4 pages, {total} visuals, {len(MEASURES)} measures.')

def main(data_folder=None):
    (ROOT/'docs').mkdir(exist_ok=True)
    build_model(data_folder);build_report()

if __name__=='__main__':main()
