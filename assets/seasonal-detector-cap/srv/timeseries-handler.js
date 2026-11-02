'use strict';

/**
 * Handler for TimeSeriesService — reads /DMF/TS_PS from on-premise CAR HANA
 * through BTP Connectivity Service + Cloud Connector.
 *
 * HANA connection helpers are shared via ./hana-client.js.
 * No credentials are hardcoded — the BTP Destination Service supplies everything.
 */

const cds = require('@sap/cds');
const { resolveHanaDestination, openHanaConnection, execSql } = require('./hana-client');

// SAP serial date ↔ ISO-8601 conversion
// SAP/CAR stores dates as Excel serial numbers (epoch: 1899-12-30).
const SAP_EPOCH_MS = Date.UTC(1899, 11, 30);

function sapSerialToISO(serial) {
  const ms = SAP_EPOCH_MS + Math.floor(serial) * 86400000;
  return new Date(ms).toISOString().slice(0, 10);
}

function isoToSapSerial(isoDate) {
  const d = new Date(isoDate + 'T00:00:00Z');
  return Math.round((d.getTime() - SAP_EPOCH_MS) / 86400000);
}

async function queryTimeSeriesFromHana(conn, { articleIds, storeIds, startSerial, endSerial, granularity }) {
  const artPlaceholders = articleIds.map(() => '?').join(', ');
  const locPlaceholders = storeIds.map(() => '?').join(', ');

  const sql = `
    SELECT
      PROD_ID,
      LOC_ID,
      TSTFR,
      SUM(UNIT_SALES)   AS UNIT_SALES,
      SUM(REVENUE_NET)  AS REVENUE_NET
    FROM "/DMF/TS_PS"
    WHERE
      MANDT = '100'
      AND PROD_ID IN (${artPlaceholders})
      AND LOC_ID   IN (${locPlaceholders})
      AND TSTFR >= ?
      AND TSTFR <= ?
      AND TIME_GRAN = ?
      AND UNIT_SALES > 0
    GROUP BY PROD_ID, LOC_ID, TSTFR
    ORDER BY PROD_ID, LOC_ID, TSTFR
  `;

  const params = [...articleIds, ...storeIds, startSerial, endSerial, granularity || 'D'];
  return await execSql(conn, sql, params);
}

module.exports = cds.service.impl(async function (srv) {

  srv.on('readTimeSeries', async (req) => {
    const { articleIds, storeIds, startDate, endDate, granularity } = req.data;

    if (!articleIds?.length || !storeIds?.length) {
      return req.error(400, 'articleIds and storeIds must be non-empty arrays.');
    }

    const startSerial = isoToSapSerial(startDate);
    const endSerial   = isoToSapSerial(endDate) + 0.99999;

    let dest, conn;
    try {
      dest = await resolveHanaDestination();
    } catch (err) {
      cds.log('timeseries').error('Destination resolution failed:', err.message);
      return req.error(503, `Cannot reach CAR HANA destination: ${err.message}`);
    }

    try {
      conn = await openHanaConnection(dest);
    } catch (err) {
      cds.log('timeseries').error('HANA connection failed:', err.message);
      return req.error(503, `HANA connection failed: ${err.message}`);
    }

    let rows;
    try {
      rows = await queryTimeSeriesFromHana(conn, { articleIds, storeIds, startSerial, endSerial, granularity });
    } finally {
      conn.disconnect();
    }

    return rows.map((row) => ({
      articleId:     row.PROD_ID,
      storeId:       row.LOC_ID,
      date:          sapSerialToISO(row.TSTFR),
      salesQuantity: parseFloat(row.UNIT_SALES   ?? 0),
      salesValue:    parseFloat(row.REVENUE_NET  ?? 0),
    }));
  });
});
