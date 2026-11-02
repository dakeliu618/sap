using { seasonal.detector as db } from '../db/schema';

// ─────────────────────────────────────────────────────────────
// Time-series read service  (proxies CAR HANA on-premise data)
// ─────────────────────────────────────────────────────────────
service TimeSeriesService @(path: '/api/timeseries') {

  @readonly
  action readTimeSeries(
    articleIds : array of String,
    storeIds   : array of String,
    startDate  : String,
    endDate    : String,
    granularity: String default 'D'
  ) returns array of {
    articleId      : String;
    storeId        : String;
    date           : String;
    salesQuantity  : Decimal;
    salesValue     : Decimal;
  };
}

// ─────────────────────────────────────────────────────────────
// Classification results service
// All four actions are backed by direct SQL in classification-handler.js
// against Z-tables on the on-premise HANA (same Cloud Connector tunnel).
// ─────────────────────────────────────────────────────────────
service ClassificationService @(path: '/api/classifications') {

  // Create a new run or update an existing one
  action upsertRun(run : {
    ID                    : UUID;
    status                : String;
    startedAt             : Timestamp;
    completedAt           : Timestamp;
    totalProcessed        : Integer;
    coveragePct           : Decimal;
    seasonalCount         : Integer;
    nonSeasonalCount      : Integer;
    insufficientDataCount : Integer;
    lowConfidenceCount    : Integer;
    errorDetail           : String;
  }) returns { ID : UUID; status : String };

  // Bulk-write results for a completed run
  action saveResults(
    runId   : UUID,
    results : array of {
      articleId             : String;
      storeId               : String;
      classification        : String;
      confidenceScore       : Decimal;
      seasonStartWeek       : Integer;
      seasonEndWeek         : Integer;
      seasonalStrengthIndex : Decimal;
      algorithmUsed         : String;
      dataRangeStart        : String;
      dataRangeEnd          : String;
    }
  ) returns { count : Integer };

  // Query results with optional filters
  action getResults(
    runId          : UUID;
    classification : String;
    minConfidence  : Decimal;
    articleId      : String;
    storeId        : String
  ) returns array of {
    ID                    : UUID;
    runId                 : UUID;
    articleId             : String;
    storeId               : String;
    classification        : String;
    confidenceScore       : Decimal;
    seasonStartWeek       : Integer;
    seasonEndWeek         : Integer;
    seasonalStrengthIndex : Decimal;
    algorithmUsed         : String;
    dataRangeStart        : String;
    dataRangeEnd          : String;
    workflowStatus        : String;
    notificationStatus    : String;
    createdAt             : Timestamp;
  };

  // Get a specific run or the latest run (omit runId for latest)
  action getRun(runId : UUID) returns {
    ID                    : UUID;
    status                : String;
    startedAt             : Timestamp;
    completedAt           : Timestamp;
    totalProcessed        : Integer;
    coveragePct           : Decimal;
    seasonalCount         : Integer;
    nonSeasonalCount      : Integer;
    insufficientDataCount : Integer;
    lowConfidenceCount    : Integer;
    errorDetail           : String;
    createdAt             : Timestamp;
    modifiedAt            : Timestamp;
  };
}
