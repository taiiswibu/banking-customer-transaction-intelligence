-- SQLite 3.25+. Run through scripts/run_sql.py or open data/analytics.sqlite in DBeaver.
-- AmountCents is integer: all authoritative money reconciliation is in cents.
-- Q01: Executive KPIs; no recorded error is a proxy, not proof of settlement
SELECT COUNT(*) Attempts, SUM(HasError) ErrorAttempts,
 ROUND(100.0*SUM(HasError)/COUNT(*),4) ErrorRatePct,
 SUM(CASE WHEN HasError=0 AND AmountCents>0 THEN AmountCents ELSE 0 END)/100.0 PositiveVolume,
 SUM(CASE WHEN HasError=0 THEN AmountCents ELSE 0 END)/100.0 NetVolume,
 COUNT(DISTINCT ClientID) ObservedCustomers,COUNT(DISTINCT CardID) ObservedCards
FROM FactTransaction;

-- Q02: Transactions in calendar year 2023 (half-open interval)
SELECT COUNT(*) Attempts,SUM(HasError) ErrorAttempts FROM FactTransaction
WHERE Date>='2023-01-01' AND Date<'2024-01-01';

-- Q03: Top five physical merchant cities; same city names in different states stay separate
SELECT MerchantCity,MerchantState,COUNT(*) Attempts FROM FactTransaction
WHERE upper(MerchantCity)<>'ONLINE'
GROUP BY MerchantCity,MerchantState ORDER BY Attempts DESC,MerchantCity LIMIT 5;

-- Q04: Customer credit score distribution (all customer snapshot rows)
SELECT CreditBand,COUNT(*) Customers,ROUND(AVG(CreditScore),1) MeanScore
FROM DimCustomer GROUP BY CreditBand ORDER BY MIN(CreditScore);

-- Q05: Card portfolio by brand and type; counts are not transaction counts
SELECT Brand,CardType,COUNT(*) Cards,SUM(ObservedActive) ObservedCards
FROM DimCard GROUP BY Brand,CardType ORDER BY Cards DESC;

-- Q06: Recorded error rate by channel; denominator is all attempts
SELECT Channel,COUNT(*) Attempts,SUM(HasError) ErrorAttempts,
 ROUND(100.0*SUM(HasError)/COUNT(*),4) ErrorRatePct
FROM FactTransaction GROUP BY Channel ORDER BY ErrorRatePct DESC;

-- Q07: Top ten customers within each month using window ranking
WITH s AS (SELECT substr(Date,1,7) Month,ClientID,SUM(AmountCents) PositiveCents
 FROM FactTransaction WHERE AmountCents>0 AND HasError=0 GROUP BY 1,2),
r AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY Month ORDER BY PositiveCents DESC,ClientID) Position FROM s)
SELECT Month,ClientID,Position,PositiveCents/100.0 PositiveVolume FROM r WHERE Position<=10 ORDER BY Month,Position;

-- Q08: Top merchant categories by positive no-error transaction volume (includes transfers)
SELECT MCC,Description,COUNT(*) Attempts,SUM(CASE WHEN HasError=0 AND AmountCents>0 THEN AmountCents ELSE 0 END)/100.0 PositiveVolume
FROM v_transactions GROUP BY MCC,Description ORDER BY PositiveVolume DESC LIMIT 10;

-- Q09: Last 30 observed days spend-to-limit proxy on CREDIT cards only
-- This is transaction volume / current snapshot limit; it is NOT credit utilization or default risk.
WITH s AS (SELECT CardID,SUM(AmountCents) PositiveCents FROM FactTransaction
 WHERE HasError=0 AND AmountCents>0 AND Date>=date((SELECT MAX(Date) FROM FactTransaction),'-29 days') GROUP BY CardID)
SELECT c.CardID,c.ClientID,c.CreditLimit,COALESCE(s.PositiveCents,0)/100.0 Positive30d,
 ROUND(COALESCE(s.PositiveCents,0)/100.0/NULLIF(c.CreditLimit,0),4) VolumeToLimitProxy
FROM DimCard c LEFT JOIN s USING(CardID) WHERE c.CardType='Credit' AND c.CreditLimit>0
ORDER BY VolumeToLimitProxy DESC,c.CardID;

-- Q10: Long-open cards with NO OBSERVED transactions in export; not proven lifetime dormancy
SELECT Brand,CardType,COUNT(*) LongOpenUnobserved FROM DimCard
WHERE LongOpenUnobserved=1 GROUP BY Brand,CardType ORDER BY LongOpenUnobserved DESC;

-- Q11: Multi-state card-days; only known US states and physical merchant-city rows
SELECT CardID,Date,COUNT(DISTINCT MerchantState) States,COUNT(*) Attempts
FROM FactTransaction WHERE IsPhysicalUS=1 GROUP BY CardID,Date
HAVING COUNT(DISTINCT MerchantState)>=2 ORDER BY States DESC,Date,CardID;

-- Q12: Monthly volume and running total; integer cents before presentation
SELECT Month,PositiveCents/100.0 PositiveVolume,
 SUM(PositiveCents) OVER(ORDER BY Month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)/100.0 RunningPositiveVolume,
 PositiveCents/100.0-LAG(PositiveCents/100.0) OVER(ORDER BY Month) ChangeVsPreviousMonth
FROM v_monthly ORDER BY Month;

-- Q13: Observed customers with a gap >90 days as of export end; this is a follow-up list, not churn labels
SELECT ClientID,MAX(Date) LastObservedDate,
 CAST(julianday((SELECT MAX(Date) FROM FactTransaction))-julianday(MAX(Date)) AS INTEGER) GapDays,
 COUNT(*) HistoricalAttempts FROM FactTransaction GROUP BY ClientID
HAVING GapDays>90 ORDER BY GapDays DESC,ClientID;

-- Q14: High-value review candidates; threshold is frozen full-export MCC P99 with n>=30
SELECT t.TransactionID,t.Date,t.CardID,m.Description,t.Amount,m.P99Amount,m.ReferenceCount
FROM FactTransaction t JOIN DimMCC m USING(MCC)
WHERE t.HighValueFlag=1 ORDER BY t.AmountCents DESC,t.TransactionID;

-- Q15: Inputs for customer credit score vs positive volume; observed customers only
SELECT u.ClientID,u.CreditScore,u.YearlyIncome,SUM(CASE WHEN t.HasError=0 AND t.AmountCents>0 THEN t.AmountCents ELSE 0 END)/100.0 PositiveVolume,
 COUNT(*) Attempts FROM DimCustomer u JOIN FactTransaction t USING(ClientID)
GROUP BY u.ClientID,u.CreditScore,u.YearlyIncome ORDER BY u.ClientID;

-- Q16: State x category volume matrix for physical US transactions
SELECT MerchantState,MerchantGroup,SUM(CASE WHEN HasError=0 AND AmountCents>0 THEN AmountCents ELSE 0 END)/100.0 PositiveVolume,
 COUNT(*) Attempts FROM v_transactions WHERE IsPhysicalUS=1
GROUP BY MerchantState,MerchantGroup ORDER BY MerchantState,MerchantGroup;

-- Q17: Split error mentions; multi-error transactions contribute to multiple groups
SELECT e.Error,COUNT(*) Mentions,COUNT(DISTINCT e.TransactionID) AffectedAttempts
FROM FactError e GROUP BY e.Error ORDER BY Mentions DESC;

-- Q18: Monthly year-over-year (same calendar month) using self join, not 12-row assumption
SELECT a.Month,a.PositiveCents/100.0 PositiveVolume,b.PositiveCents/100.0 PriorYearVolume,
 ROUND(1.0*a.PositiveCents/NULLIF(b.PositiveCents,0)-1,6) YoYRate
FROM v_monthly a LEFT JOIN v_monthly b ON b.Month=strftime('%Y-%m',date(a.Month||'-01','-1 year')) ORDER BY a.Month;

-- Q19: Comparable Jan-Oct 2023 vs Jan-Oct 2024; avoid incomplete-year comparison
SELECT substr(Date,1,4) Year,COUNT(*) Attempts,SUM(HasError) ErrorAttempts,
 SUM(CASE WHEN HasError=0 AND AmountCents>0 THEN AmountCents ELSE 0 END)/100.0 PositiveVolume
FROM FactTransaction WHERE (Date>='2023-01-01' AND Date<'2023-11-01') OR (Date>='2024-01-01' AND Date<'2024-11-01')
GROUP BY substr(Date,1,4) ORDER BY Year;

-- Q20: Snapshot status by card type (snapshot fixed to data max, independent of report date slicer)
SELECT CardType,SnapshotStatus,COUNT(*) Cards FROM DimCard GROUP BY CardType,SnapshotStatus ORDER BY CardType,SnapshotStatus;

-- Q21: Verify rolling 60-minute error bursts (third and later error in window), including simultaneous timestamps ordered by ID
SELECT a.TransactionID,a.CardID,a.Timestamp,COUNT(b.TransactionID) ErrorsInWindow
FROM FactTransaction a JOIN FactTransaction b ON b.CardID=a.CardID AND b.HasError=1
AND b.Timestamp>=datetime(a.Timestamp,'-60 minutes') AND (b.Timestamp<a.Timestamp OR (b.Timestamp=a.Timestamp AND b.TransactionID<=a.TransactionID))
WHERE a.HasError=1 GROUP BY a.TransactionID,a.CardID,a.Timestamp HAVING COUNT(b.TransactionID)>=3 ORDER BY a.Timestamp,a.TransactionID;

-- Q22: Money reconciliation: positive + negative equals net for rows without recorded errors
SELECT SUM(CASE WHEN HasError=0 AND AmountCents>0 THEN AmountCents ELSE 0 END) PositiveCents,
 SUM(CASE WHEN HasError=0 AND AmountCents<0 THEN AmountCents ELSE 0 END) NegativeCents,
 SUM(CASE WHEN HasError=0 THEN AmountCents ELSE 0 END) NetCents,
 SUM(CASE WHEN HasError=1 THEN AmountCents ELSE 0 END) ErrorRowCents,
 SUM(AmountCents) AllRecordedCents FROM FactTransaction;

-- Q23: Review rules overlap; union count must not be sum of rule counts
SELECT ReviewReason,COUNT(*) Attempts FROM FactTransaction WHERE ReviewFlag=1
GROUP BY ReviewReason ORDER BY Attempts DESC;

-- Q24: Observed card coverage by month; denominator is full snapshot portfolio (not historically eligible cards)
SELECT substr(t.Date,1,7) Month,COUNT(DISTINCT t.CardID) ObservedCards,
 ROUND(100.0*COUNT(DISTINCT t.CardID)/(SELECT COUNT(*) FROM DimCard),4) ObservedCoveragePct
FROM FactTransaction t GROUP BY 1 ORDER BY 1;

-- Q25: Customer concentration and cumulative share of positive no-error volume
WITH s AS (SELECT ClientID,SUM(AmountCents) VolumeCents FROM FactTransaction WHERE HasError=0 AND AmountCents>0 GROUP BY ClientID)
SELECT ClientID,VolumeCents/100.0 PositiveVolume,
 ROW_NUMBER() OVER(ORDER BY VolumeCents DESC,ClientID) Position,
 ROUND(1.0*SUM(VolumeCents) OVER(ORDER BY VolumeCents DESC,ClientID ROWS UNBOUNDED PRECEDING)/SUM(VolumeCents) OVER(),6) CumulativeShare
FROM s ORDER BY Position;

-- Q26: Join multiplication guard: each transaction remains one row in the enriched view
SELECT (SELECT COUNT(*) FROM FactTransaction) FactRows,(SELECT COUNT(*) FROM v_transactions) JoinedRows,
 (SELECT COUNT(DISTINCT TransactionID) FROM v_transactions) DistinctJoinedTransactions;
