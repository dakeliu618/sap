'use strict';

/**
 * Handler for ClassificationService — persists and retrieves
 * seasonal classification results in the CAP-owned HANA Cloud DB.
 */

const cds = require('@sap/cds');

module.exports = cds.service.impl(async function (srv) {

  const { ClassificationRun, ClassificationResult } = srv.entities;

  // ── Upsert a run header ──────────────────────────────────────────────────
  srv.on('upsertRun', async (req) => {
    const run = req.data.run;
    if (!run.ID) {
      // New run
      return await INSERT.into(ClassificationRun).entries(run);
    }
    // Update existing run
    await UPDATE(ClassificationRun)
      .set({
        status:               run.status,
        completedAt:          run.completedAt,
        totalProcessed:       run.totalProcessed,
        coveragePct:          run.coveragePct,
        seasonalCount:        run.seasonalCount,
        nonSeasonalCount:     run.nonSeasonalCount,
        insufficientDataCount: run.insufficientDataCount,
        lowConfidenceCount:   run.lowConfidenceCount,
        errorDetail:          run.errorDetail,
      })
      .where({ ID: run.ID });
    return run;
  });

  // ── Bulk-write classification results ───────────────────────────────────
  srv.on('saveResults', async (req) => {
    const { runId, results } = req.data;

    if (!runId || !results?.length) {
      return req.error(400, 'runId and a non-empty results array are required.');
    }

    // Stamp each result with the run association and creation timestamp
    const stamped = results.map((r) => ({
      ...r,
      run_ID:    runId,
      createdAt: new Date().toISOString(),
    }));

    await INSERT.into(ClassificationResult).entries(stamped);
    return { count: stamped.length };
  });

});
