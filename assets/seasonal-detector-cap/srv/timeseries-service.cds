using { seasonal.detector as db } from '../db/schema';

// ─────────────────────────────────────────────────────────────
// Time-series read service  (proxies CAR HANA on-premise data)
// ─────────────────────────────────────────────────────────────
service TimeSeriesService @(path: '/api/timeseries') {

  // Read article/store time-series from CAR via on-premise connector.
  // Bound to a custom handler in timeseries-handler.js that routes
  // through BTP Connectivity → Cloud Connector → CAR HANA.
  @readonly
  action readTimeSeries(
    articleIds : array of String,  // e.g. ['069DF1A4...', '069DF2B5...']
    storeIds   : array of String,  // e.g. ['069DF1A4...']
    startDate  : String,           // ISO-8601 e.g. '2022-01-01'
    endDate    : String,           // ISO-8601 e.g. '2024-12-31'
    granularity: String default 'D'  // 'D' daily, 'W' weekly
  ) returns array of {
    articleId      : String;
    storeId        : String;
    date           : String;  // ISO-8601 calendar date
    salesQuantity  : Decimal;
    salesValue     : Decimal;
  };
}

// ─────────────────────────────────────────────────────────────
// Classification results service  (read/write — CAP-owned DB)
// ─────────────────────────────────────────────────────────────
service ClassificationService @(path: '/api/classifications') {

  entity Runs    as projection on db.ClassificationRun
    excluding { results };

  entity Results as projection on db.ClassificationResult;

  // Create or update a run header
  action upsertRun(run : db.ClassificationRun) returns db.ClassificationRun;

  // Bulk-write results for a completed run
  action saveResults(
    runId   : UUID,
    results : array of db.ClassificationResult
  ) returns { count : Integer };
}
