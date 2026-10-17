namespace seasonal.detector;

using { cuid, managed } from '@sap/cds/common';

// ─────────────────────────────────────────────────────────────
// CAR on-premise table — CAP does NOT own this, it already
// exists in the CAR HANA schema. @cds.persistence.exists tells
// CAP not to CREATE or ALTER it, only generate SQL queries.
// ─────────────────────────────────────────────────────────────
@cds.persistence.exists
@readonly
entity CAR_TimeSeries {
  key MANDT          : String(3);
  key PROD_ID        : String(32);   // Article ID
  key LOC_ID         : String(32);   // Store/location ID
  key SALES_ORG_ID   : String(32);
  key DISTR_CHNL_ID  : String(10);
  key ORDER_CHNL_ID  : Integer;
  key TSTFR          : Decimal(15,5); // SAP serial date (Excel epoch 1899-12-30)
  key TIME_GRAN      : String(1);    // 'D' = daily, 'W' = weekly
      TSTTO          : Decimal(15,5);
      UNIT_SALES     : Decimal(13,3);
      UOM            : String(3);
      TXN_COUNT      : Integer;
      REVENUE_NET    : Decimal(15,2);
      REVENUE_TAX    : Decimal(15,2);
      COST_PRC_PER_UNIT : Decimal(15,5);
      RETURNED_SALE  : String(1);    // 'X' = return
      OOS_PCT        : Decimal(5,2);
}

// ─────────────────────────────────────────────────────────────
// Classification results — owned and managed by this CAP app
// ─────────────────────────────────────────────────────────────
entity ClassificationRun : cuid, managed {
  status         : String(20) enum {
    RUNNING      = 'RUNNING';
    COMPLETED    = 'COMPLETED';
    FAILED       = 'FAILED';
  };
  startedAt      : Timestamp;
  completedAt    : Timestamp;
  totalProcessed : Integer default 0;
  coveragePct    : Decimal(5,2) default 0;
  seasonalCount  : Integer default 0;
  nonSeasonalCount : Integer default 0;
  insufficientDataCount : Integer default 0;
  lowConfidenceCount : Integer default 0;
  errorDetail    : String(500);
  results        : Composition of many ClassificationResult on results.run = $self;
}

entity ClassificationResult : cuid {
  run                  : Association to ClassificationRun;
  articleId            : String(32);
  storeId              : String(32);
  classification       : String(30) enum {
    SEASONAL           = 'SEASONAL';
    NON_SEASONAL       = 'NON_SEASONAL';
    LOW_CONFIDENCE_SEASONAL = 'LOW_CONFIDENCE_SEASONAL';
    INSUFFICIENT_DATA  = 'INSUFFICIENT_DATA';
  };
  confidenceScore      : Decimal(5,2);
  seasonStartWeek      : Integer;
  seasonEndWeek        : Integer;
  seasonalStrengthIndex : Decimal(6,4);
  algorithmUsed        : String(20);
  dataRangeStart       : String(10);
  dataRangeEnd         : String(10);
  workflowStatus       : String(30) enum {
    PENDING_WORKFLOW   = 'PENDING_WORKFLOW';
    WORKFLOW_TRIGGERED = 'WORKFLOW_TRIGGERED';
    WORKFLOW_FAILED    = 'WORKFLOW_FAILED';
    NOT_APPLICABLE     = 'NOT_APPLICABLE';
  } default 'NOT_APPLICABLE';
  notificationStatus   : String(30) enum {
    PENDING_NOTIFICATION   = 'PENDING_NOTIFICATION';
    NOTIFICATION_SENT      = 'NOTIFICATION_SENT';
    NOTIFICATION_FAILED    = 'NOTIFICATION_FAILED';
    NOT_APPLICABLE         = 'NOT_APPLICABLE';
  } default 'NOT_APPLICABLE';
  createdAt            : Timestamp;
}
