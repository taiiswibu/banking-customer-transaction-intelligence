-- Generated SQLite DDL. Run on an empty database; data loading is handled by scripts/pipeline.py.

CREATE TABLE "DimCard" ("CardID" INTEGER,"ClientID" INTEGER,"Brand" TEXT,"CardType" TEXT,"HasChip" TEXT,"CreditLimit" REAL,"OpenedDate" TEXT,"Expires" TEXT,"ObservedTransactions" INTEGER,"ObservedActive" INTEGER,"LastObservedDate" TEXT,"DaysSinceObserved" INTEGER,"SnapshotStatus" TEXT,"LongOpenUnobserved" INTEGER);

CREATE TABLE "DimCustomer" ("ClientID" INTEGER,"SnapshotAge" INTEGER,"AgeBand" TEXT,"Gender" TEXT,"YearlyIncome" REAL,"TotalDebt" REAL,"CreditScore" INTEGER,"CreditBand" TEXT,"ReportedCreditCards" INTEGER);

CREATE TABLE "DimDate" ("Date" TEXT,"Year" INTEGER,"MonthNumber" INTEGER,"Month" TEXT,"YearMonth" TEXT,"MonthStart" TEXT,"Weekday" TEXT);

CREATE TABLE "DimMCC" ("MCC" INTEGER,"Description" TEXT,"MerchantGroup" TEXT,"P99Amount" REAL,"ReferenceCount" INTEGER);

CREATE TABLE "DimRule" ("Rule" TEXT);

CREATE TABLE "FactError" ("TransactionID" INTEGER,"Error" TEXT);

CREATE TABLE "FactTransaction" ("TransactionID" INTEGER,"Timestamp" TEXT,"Date" TEXT,"ClientID" INTEGER,"CardID" INTEGER,"AmountCents" INTEGER,"Amount" REAL,"Channel" TEXT,"MerchantID" INTEGER,"MerchantCity" TEXT,"MerchantState" TEXT,"MCC" INTEGER,"Errors" TEXT,"HasError" INTEGER,"ErrorCount" INTEGER,"PrimaryError" TEXT,"AmountType" TEXT,"IsPhysicalUS" INTEGER,"HighValueFlag" INTEGER,"MultiStateFlag" INTEGER,"ErrorBurstFlag" INTEGER,"ReviewFlag" INTEGER,"ReviewStatus" TEXT,"ReviewReason" TEXT);

CREATE INDEX idx_tx_CardID ON FactTransaction(CardID);

CREATE INDEX idx_tx_ClientID ON FactTransaction(ClientID);

CREATE INDEX idx_tx_Date ON FactTransaction(Date);

CREATE INDEX idx_tx_MCC ON FactTransaction(MCC);

CREATE INDEX idx_tx_TransactionID ON FactTransaction(TransactionID);

CREATE VIEW v_monthly AS
    SELECT substr(Date,1,7) AS Month,COUNT(*) Attempts,SUM(HasError) ErrorAttempts,
      SUM(CASE WHEN HasError=0 AND AmountCents>0 THEN AmountCents ELSE 0 END) PositiveCents,
      SUM(CASE WHEN HasError=0 THEN AmountCents ELSE 0 END) NetCents,
      COUNT(DISTINCT ClientID) ActiveCustomers,SUM(ReviewFlag) ReviewAttempts
    FROM FactTransaction GROUP BY substr(Date,1,7);

CREATE VIEW v_transactions AS
    SELECT t.*, c.Brand,c.CardType,c.CreditLimit,u.AgeBand,u.CreditBand,u.CreditScore,u.YearlyIncome,m.Description,m.MerchantGroup
    FROM FactTransaction t JOIN DimCard c USING(CardID) JOIN DimCustomer u ON c.ClientID=u.ClientID JOIN DimMCC m USING(MCC);
