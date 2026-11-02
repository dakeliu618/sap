'use strict';

/**
 * Handler for ClassificationService — persists and retrieves seasonal classification
 * results in the on-premise HANA DB via the same Cloud Connector tunnel used for
 * reading /DMF/TS_PS.
 *
 * Tables (created by db/ddl.sql — run once by a DBA before first deployment):
 *   ZSEASONAL_CLASS_RUN    — one row per classification run
 *   ZSEASONAL_CLASS_RESULT — one row per article/store classification result
 *
 * Destination used for writes: env var CAR_HANA_WRITE_DESTINATION_NAME
 *   defaults to CAR_HANA_DESTINATION_NAME, then 'CAR_HANA'.
 * The HANA user behind that destination needs:
 *   SELECT, INSERT, UPDATE on ZSEASONAL_CLASS_RUN
 *   SELECT, INSERT         on ZSEASONAL_CLASS_RESULT
 */

'use strict';

const cds  = require('@sap/cds');
const { randomUUID } = require('crypto');
const { connect, execSql } = require('./hana-client');

const log = cds.log('classification');

function writeDestination() {
  return process.env.CAR_HANA_WRITE_DESTINATION_NAME
      || process.env.CAR_HANA_DESTINATION_NAME
      || 'CAR_HANA';
}

async function withConn(fn) {
  const conn = await connect(writeDestination());
  try {
    return await fn(conn);
  } finally {
    conn.disconnect();
  }
}

module.exports = cds.service.impl(async function (srv) {

  // ── upsertRun ─────────────────────────────────────────────────────────────
  // Creates a new run header or updates an existing one.
  srv.on('upsertRun', async (req) => {
    const r = req.data.run;
    const id = r.ID || randomUUID();

    await withConn(async (conn) => {
      // Try UPDATE first; if no rows affected, INSERT
      const updated = await execSql(conn, `
        UPDATE "ZSEASONAL_CLASS_RUN" SET
          "STATUS"                  = ?,
          "COMPLETED_AT"            = ?,
          "TOTAL_PROCESSED"         = ?,
          "COVERAGE_PCT"            = ?,
          "SEASONAL_COUNT"          = ?,
          "NON_SEASONAL_COUNT"      = ?,
          "INSUFFICIENT_DATA_COUNT" = ?,
          "LOW_CONFIDENCE_COUNT"    = ?,
          "ERROR_DETAIL"            = ?,
          "MODIFIED_AT"             = CURRENT_TIMESTAMP
        WHERE "ID" = ?
      `, [
        r.status            ?? 'RUNNING',
        r.completedAt       ?? null,
        r.totalProcessed    ?? 0,
        r.coveragePct       ?? 0,
        r.seasonalCount     ?? 0,
        r.nonSeasonalCount  ?? 0,
        r.insufficientDataCount ?? 0,
        r.lowConfidenceCount ?? 0,
        r.errorDetail       ?? null,
        id,
      ]);

      // updated is an array of affected rows on HANA client; length 0 = nothing updated
      if (!updated?.length) {
        await execSql(conn, `
          INSERT INTO "ZSEASONAL_CLASS_RUN"
            ("ID","STATUS","STARTED_AT","COMPLETED_AT","TOTAL_PROCESSED","COVERAGE_PCT",
             "SEASONAL_COUNT","NON_SEASONAL_COUNT","INSUFFICIENT_DATA_COUNT","LOW_CONFIDENCE_COUNT",
             "ERROR_DETAIL","CREATED_AT","MODIFIED_AT")
          VALUES (?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
        `, [
          id,
          r.status            ?? 'RUNNING',
          r.startedAt         ?? null,
          r.completedAt       ?? null,
          r.totalProcessed    ?? 0,
          r.coveragePct       ?? 0,
          r.seasonalCount     ?? 0,
          r.nonSeasonalCount  ?? 0,
          r.insufficientDataCount ?? 0,
          r.lowConfidenceCount ?? 0,
          r.errorDetail       ?? null,
        ]);
      }
    });

    log.info('upsertRun — id=%s status=%s', id, r.status);
    return { ID: id, status: r.status ?? 'RUNNING' };
  });

  // ── saveResults ───────────────────────────────────────────────────────────
  // Bulk-inserts classification results for a completed run.
  srv.on('saveResults', async (req) => {
    const { runId, results } = req.data;
    if (!runId || !results?.length) {
      return req.error(400, 'runId and a non-empty results array are required.');
    }

    await withConn(async (conn) => {
      for (const r of results) {
        await execSql(conn, `
          INSERT INTO "ZSEASONAL_CLASS_RESULT"
            ("ID","RUN_ID","ARTICLE_ID","STORE_ID","CLASSIFICATION","CONFIDENCE_SCORE",
             "SEASON_START_WEEK","SEASON_END_WEEK","SEASONAL_STRENGTH_INDEX","ALGORITHM_USED",
             "DATA_RANGE_START","DATA_RANGE_END","WORKFLOW_STATUS","NOTIFICATION_STATUS","CREATED_AT")
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
        `, [
          randomUUID(),
          runId,
          r.articleId,
          r.storeId,
          r.classification,
          r.confidenceScore     ?? null,
          r.seasonStartWeek     ?? null,
          r.seasonEndWeek       ?? null,
          r.seasonalStrengthIndex ?? null,
          r.algorithmUsed       ?? 'stl',
          r.dataRangeStart      ?? null,
          r.dataRangeEnd        ?? null,
          r.workflowStatus      ?? 'NOT_APPLICABLE',
          r.notificationStatus  ?? 'NOT_APPLICABLE',
        ]);
      }
    });

    log.info('saveResults — runId=%s count=%d', runId, results.length);
    return { count: results.length };
  });

  // ── getResults ────────────────────────────────────────────────────────────
  // Returns classification results with optional filters.
  srv.on('getResults', async (req) => {
    const { runId, classification, minConfidence, articleId, storeId } = req.data;

    const conditions = [];
    const params     = [];

    if (runId)          { conditions.push('"RUN_ID" = ?');                  params.push(runId); }
    if (classification) { conditions.push('"CLASSIFICATION" = ?');          params.push(classification); }
    if (minConfidence)  { conditions.push('"CONFIDENCE_SCORE" >= ?');       params.push(minConfidence); }
    if (articleId)      { conditions.push('"ARTICLE_ID" = ?');              params.push(articleId); }
    if (storeId)        { conditions.push('"STORE_ID" = ?');                params.push(storeId); }

    const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';

    return await withConn(async (conn) => {
      const rows = await execSql(conn, `
        SELECT
          "ID", "RUN_ID", "ARTICLE_ID", "STORE_ID", "CLASSIFICATION",
          "CONFIDENCE_SCORE", "SEASON_START_WEEK", "SEASON_END_WEEK",
          "SEASONAL_STRENGTH_INDEX", "ALGORITHM_USED",
          "DATA_RANGE_START", "DATA_RANGE_END",
          "WORKFLOW_STATUS", "NOTIFICATION_STATUS", "CREATED_AT"
        FROM "ZSEASONAL_CLASS_RESULT"
        ${where}
        ORDER BY "CREATED_AT" DESC
      `, params);

      return rows.map((row) => ({
        ID:                    row.ID,
        runId:                 row.RUN_ID,
        articleId:             row.ARTICLE_ID,
        storeId:               row.STORE_ID,
        classification:        row.CLASSIFICATION,
        confidenceScore:       row.CONFIDENCE_SCORE     != null ? parseFloat(row.CONFIDENCE_SCORE)     : null,
        seasonStartWeek:       row.SEASON_START_WEEK    != null ? parseInt(row.SEASON_START_WEEK, 10)  : null,
        seasonEndWeek:         row.SEASON_END_WEEK      != null ? parseInt(row.SEASON_END_WEEK, 10)    : null,
        seasonalStrengthIndex: row.SEASONAL_STRENGTH_INDEX != null ? parseFloat(row.SEASONAL_STRENGTH_INDEX) : null,
        algorithmUsed:         row.ALGORITHM_USED,
        dataRangeStart:        row.DATA_RANGE_START,
        dataRangeEnd:          row.DATA_RANGE_END,
        workflowStatus:        row.WORKFLOW_STATUS,
        notificationStatus:    row.NOTIFICATION_STATUS,
        createdAt:             row.CREATED_AT,
      }));
    });
  });

  // ── getRun ────────────────────────────────────────────────────────────────
  // Returns the latest run or a specific run by ID.
  srv.on('getRun', async (req) => {
    const { runId } = req.data;

    return await withConn(async (conn) => {
      const sql = runId
        ? `SELECT * FROM "ZSEASONAL_CLASS_RUN" WHERE "ID" = ?`
        : `SELECT * FROM "ZSEASONAL_CLASS_RUN" ORDER BY "CREATED_AT" DESC LIMIT 1`;

      const rows = await execSql(conn, sql, runId ? [runId] : []);
      if (!rows.length) return null;

      const row = rows[0];
      return {
        ID:                   row.ID,
        status:               row.STATUS,
        startedAt:            row.STARTED_AT,
        completedAt:          row.COMPLETED_AT,
        totalProcessed:       row.TOTAL_PROCESSED    != null ? parseInt(row.TOTAL_PROCESSED, 10)     : 0,
        coveragePct:          row.COVERAGE_PCT       != null ? parseFloat(row.COVERAGE_PCT)          : 0,
        seasonalCount:        row.SEASONAL_COUNT     != null ? parseInt(row.SEASONAL_COUNT, 10)      : 0,
        nonSeasonalCount:     row.NON_SEASONAL_COUNT != null ? parseInt(row.NON_SEASONAL_COUNT, 10)  : 0,
        insufficientDataCount: row.INSUFFICIENT_DATA_COUNT != null ? parseInt(row.INSUFFICIENT_DATA_COUNT, 10) : 0,
        lowConfidenceCount:   row.LOW_CONFIDENCE_COUNT != null ? parseInt(row.LOW_CONFIDENCE_COUNT, 10) : 0,
        errorDetail:          row.ERROR_DETAIL,
        createdAt:            row.CREATED_AT,
        modifiedAt:           row.MODIFIED_AT,
      };
    });
  });

});
