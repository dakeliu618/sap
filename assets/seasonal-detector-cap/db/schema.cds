namespace seasonal.detector;

// ─────────────────────────────────────────────────────────────
// CAR on-premise table — CAP does NOT own or deploy this.
// @cds.persistence.exists tells CAP to skip DDL generation.
// Accessed via timeseries-handler.js using direct HANA SQL.
// ─────────────────────────────────────────────────────────────
@cds.persistence.exists
@readonly
entity CAR_TimeSeries {
  key MANDT          : String(3);
  key PROD_ID        : String(32);
  key LOC_ID         : String(32);
  key SALES_ORG_ID   : String(32);
  key DISTR_CHNL_ID  : String(10);
  key ORDER_CHNL_ID  : Integer;
  key TSTFR          : Decimal(15,5);
  key TIME_GRAN      : String(1);
      TSTTO          : Decimal(15,5);
      UNIT_SALES     : Decimal(13,3);
      UOM            : String(3);
      TXN_COUNT      : Integer;
      REVENUE_NET    : Decimal(15,2);
      REVENUE_TAX    : Decimal(15,2);
      COST_PRC_PER_UNIT : Decimal(15,5);
      RETURNED_SALE  : String(1);
      OOS_PCT        : Decimal(5,2);
}

// ─────────────────────────────────────────────────────────────
// Classification tables — created by db/ddl.sql (run once by DBA).
// CAP does NOT manage these tables; @cds.persistence.skip prevents
// any auto-generated CRUD. Handlers in classification-handler.js
// use direct SQL via the same Cloud Connector tunnel.
// ─────────────────────────────────────────────────────────────
@cds.persistence.skip
entity ClassificationRun {
  key ID                    : UUID;
      status                : String(20) enum {
        RUNNING             = 'RUNNING';
        COMPLETED           = 'COMPLETED';
        FAILED              = 'FAILED';
      };
      startedAt             : Timestamp;
      completedAt           : Timestamp;
      totalProcessed        : Integer default 0;
      coveragePct           : Decimal(5,2) default 0;
      seasonalCount         : Integer default 0;
      nonSeasonalCount      : Integer default 0;
      insufficientDataCount : Integer default 0;
      lowConfidenceCount    : Integer default 0;
      errorDetail           : String(500);
      createdAt             : Timestamp;
      modifiedAt            : Timestamp;
}

@cds.persistence.skip
entity ClassificationResult {
  key ID                    : UUID;
      runId                 : UUID;
      articleId             : String(32);
      storeId               : String(32);
      classification        : String(30) enum {
        SEASONAL            = 'SEASONAL';
        NON_SEASONAL        = 'NON_SEASONAL';
        LOW_CONFIDENCE_SEASONAL = 'LOW_CONFIDENCE_SEASONAL';
        INSUFFICIENT_DATA   = 'INSUFFICIENT_DATA';
      };
      confidenceScore       : Decimal(5,2);
      seasonStartWeek       : Integer;
      seasonEndWeek         : Integer;
      seasonalStrengthIndex : Decimal(6,4);
      algorithmUsed         : String(20);
      dataRangeStart        : String(10);
      dataRangeEnd          : String(10);
      workflowStatus        : String(30) enum {
        PENDING_WORKFLOW    = 'PENDING_WORKFLOW';
        WORKFLOW_TRIGGERED  = 'WORKFLOW_TRIGGERED';
        WORKFLOW_FAILED     = 'WORKFLOW_FAILED';
        NOT_APPLICABLE      = 'NOT_APPLICABLE';
      } default 'NOT_APPLICABLE';
      notificationStatus    : String(30) enum {
        PENDING_NOTIFICATION  = 'PENDING_NOTIFICATION';
        NOTIFICATION_SENT     = 'NOTIFICATION_SENT';
        NOTIFICATION_FAILED   = 'NOTIFICATION_FAILED';
        NOT_APPLICABLE        = 'NOT_APPLICABLE';
      } default 'NOT_APPLICABLE';
      createdAt             : Timestamp;
}
