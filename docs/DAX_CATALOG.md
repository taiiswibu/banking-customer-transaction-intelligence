# DAX measures

Generated from scripts/build_powerbi.py. Model culture: en-US.

## Attempts

```dax
Attempts = COUNTROWS(FactTransaction)
```

Folder: Activity; format: `#,0`.

## Error Attempts

```dax
Error Attempts = COALESCE(SUM(FactTransaction[HasError]), 0)
```

Folder: Payment; format: `#,0`.

## Error Rate

```dax
Error Rate = DIVIDE([Error Attempts], [Attempts])
```

Folder: Payment; format: `0.00%`.

## No Recorded Error Attempts

```dax
No Recorded Error Attempts = [Attempts] - [Error Attempts]
```

Folder: Payment; format: `#,0`.

## Positive Volume

```dax
Positive Volume = CALCULATE(SUM(FactTransaction[Amount]), KEEPFILTERS(FactTransaction[HasError] = 0), KEEPFILTERS(FactTransaction[Amount] > 0))
```

Folder: Volume; format: `$#,0.00;($#,0.00)`.

## Negative Volume

```dax
Negative Volume = CALCULATE(SUM(FactTransaction[Amount]), KEEPFILTERS(FactTransaction[HasError] = 0), KEEPFILTERS(FactTransaction[Amount] < 0))
```

Folder: Volume; format: `$#,0.00;($#,0.00)`.

## Net Volume

```dax
Net Volume = CALCULATE(SUM(FactTransaction[Amount]), KEEPFILTERS(FactTransaction[HasError] = 0))
```

Folder: Volume; format: `$#,0.00;($#,0.00)`.

## All Recorded Volume

```dax
All Recorded Volume = SUM(FactTransaction[Amount])
```

Folder: Volume; format: `$#,0.00;($#,0.00)`.

## Error Row Volume

```dax
Error Row Volume = CALCULATE(SUM(FactTransaction[Amount]), KEEPFILTERS(FactTransaction[HasError] = 1))
```

Folder: Volume; format: `$#,0.00;($#,0.00)`.

## Average Positive Amount

```dax
Average Positive Amount = DIVIDE([Positive Volume], CALCULATE([Attempts], KEEPFILTERS(FactTransaction[HasError] = 0), KEEPFILTERS(FactTransaction[Amount] > 0)))
```

Folder: Volume; format: `$#,0.00`.

## Observed Customers

```dax
Observed Customers = DISTINCTCOUNT(FactTransaction[ClientID])
```

Folder: Activity; format: `#,0`.

## Observed Cards

```dax
Observed Cards = DISTINCTCOUNT(FactTransaction[CardID])
```

Folder: Activity; format: `#,0`.

## Portfolio Cards

```dax
Portfolio Cards = COUNTROWS(DimCard)
```

Folder: Portfolio; format: `#,0`.

## Portfolio Customers

```dax
Portfolio Customers = COUNTROWS(DimCustomer)
```

Folder: Portfolio; format: `#,0`.

## Observed Card Coverage

```dax
Observed Card Coverage = DIVIDE([Observed Cards], [Portfolio Cards])
```

Folder: Portfolio; format: `0.00%`.

## Snapshot Unobserved Cards

```dax
Snapshot Unobserved Cards = CALCULATE(COUNTROWS(DimCard), KEEPFILTERS(DimCard[ObservedActive] = 0))
```

Folder: Snapshot; format: `#,0`.

## Snapshot Recent Cards

```dax
Snapshot Recent Cards = CALCULATE(COUNTROWS(DimCard), KEEPFILTERS(DimCard[SnapshotStatus] = "Seen in last 30d"))
```

Folder: Snapshot; format: `#,0`.

## Snapshot Long Open Unobserved

```dax
Snapshot Long Open Unobserved = CALCULATE(COUNTROWS(DimCard), KEEPFILTERS(DimCard[LongOpenUnobserved] = 1))
```

Folder: Snapshot; format: `#,0`.

## Snapshot As Of

```dax
Snapshot As Of = CALCULATE(MAX(FactTransaction[Date]), REMOVEFILTERS())
```

Folder: Snapshot; format: `yyyy-MM-dd`.

## Snapshot Recent Observed Cards

```dax
Snapshot Recent Observed Cards = VAR EndDate = [Snapshot As Of]
RETURN CALCULATE([Observed Cards], REMOVEFILTERS(DimDate), DATESBETWEEN(DimDate[Date], EndDate - 29, EndDate))
```

Folder: Snapshot; format: `#,0`.

## Review Attempts

```dax
Review Attempts = COALESCE(SUM(FactTransaction[ReviewFlag]), 0)
```

Folder: Review; format: `#,0`.

## Review Rate

```dax
Review Rate = DIVIDE([Review Attempts], [Attempts])
```

Folder: Review; format: `0.00%`.

## High Value Attempts

```dax
High Value Attempts = COALESCE(SUM(FactTransaction[HighValueFlag]), 0)
```

Folder: Review; format: `#,0`.

## Multi State Attempts

```dax
Multi State Attempts = COALESCE(SUM(FactTransaction[MultiStateFlag]), 0)
```

Folder: Review; format: `#,0`.

## Error Burst Attempts

```dax
Error Burst Attempts = COALESCE(SUM(FactTransaction[ErrorBurstFlag]), 0)
```

Folder: Review; format: `#,0`.

## Rule Attempts

```dax
Rule Attempts = SWITCH(SELECTEDVALUE(DimRule[Rule]), "MCC > P99", [High Value Attempts], "Multi-state card-day", [Multi State Attempts], "3+ errors / 60 min", [Error Burst Attempts])
```

Folder: Review; format: `#,0`.

## Error Mentions

```dax
Error Mentions = COUNTROWS(FactError)
```

Folder: Payment; format: `#,0`.

## Multi Error Attempts

```dax
Multi Error Attempts = CALCULATE([Attempts], KEEPFILTERS(FactTransaction[ErrorCount] > 1))
```

Folder: Payment; format: `#,0`.

## Technical Error Attempts

```dax
Technical Error Attempts = CALCULATE([Attempts], FILTER(FactTransaction, CONTAINSSTRING(FactTransaction[Errors], "Technical Glitch")))
```

Folder: Payment; format: `#,0`.

## Primary Error Attempts

```dax
Primary Error Attempts = CALCULATE([Attempts], KEEPFILTERS(FactTransaction[HasError] = 1))
```

Folder: Payment; format: `#,0`.

## Positive Volume PY

```dax
Positive Volume PY = CALCULATE([Positive Volume], SAMEPERIODLASTYEAR(DimDate[Date]))
```

Folder: Time intelligence; format: `$#,0.00`.

## Positive Volume YoY

```dax
Positive Volume YoY = DIVIDE([Positive Volume] - [Positive Volume PY], [Positive Volume PY])
```

Folder: Time intelligence; format: `0.00%`.

## Positive Volume Running

```dax
Positive Volume Running = CALCULATE([Positive Volume], FILTER(ALLSELECTED(DimDate), DimDate[Date] <= MAX(DimDate[Date])))
```

Folder: Time intelligence; format: `$#,0.00`.

## Positive Volume Last 30d

```dax
Positive Volume Last 30d = VAR EndDate = MAX(FactTransaction[Date])
RETURN CALCULATE([Positive Volume], REMOVEFILTERS(DimDate), DATESBETWEEN(DimDate[Date], EndDate - 29, EndDate))
```

Folder: Time intelligence; format: `$#,0.00`.

## Credit Volume Last 30d

```dax
Credit Volume Last 30d = CALCULATE([Positive Volume Last 30d], KEEPFILTERS(DimCard[CardType] = "Credit"))
```

Folder: Proxy; format: `$#,0.00`.

## Credit Limit Snapshot

```dax
Credit Limit Snapshot = CALCULATE(SUM(DimCard[CreditLimit]), KEEPFILTERS(DimCard[CardType] = "Credit"))
```

Folder: Proxy; format: `$#,0.00`.

## Volume To Limit Proxy

```dax
Volume To Limit Proxy = DIVIDE([Credit Volume Last 30d], [Credit Limit Snapshot])
```

Folder: Proxy; format: `0.00%`.

## Volume Reconciliation Delta

```dax
Volume Reconciliation Delta = [Net Volume] - COALESCE([Positive Volume], 0) - COALESCE([Negative Volume], 0)
```

Folder: Validation; format: `$#,0.00`.

## Error Volume Reconciliation Delta

```dax
Error Volume Reconciliation Delta = [All Recorded Volume] - COALESCE([Net Volume], 0) - COALESCE([Error Row Volume], 0)
```

Folder: Validation; format: `$#,0.00`.
