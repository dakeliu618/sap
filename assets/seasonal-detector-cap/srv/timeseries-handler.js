'use strict';

/**
 * Handler for TimeSeriesService — reads /DMF/TS_PS from on-premise CAR HANA
 * through BTP Connectivity Service + Cloud Connector.
 *
 * Connectivity chain:
 *   CAP app (BTP CF) → Connectivity Service (SOCKS5 proxy)
 *     → Cloud Connector (on-premise) → CAR HANA port 30015
 *
 * Runtime requirements (injected via BTP service bindings):
 *   - VCAP_SERVICES.connectivity   → proxy host/port + JWT token endpoint
 *   - VCAP_SERVICES.destination    → CAR_HANA destination (host, port, user, password)
 *   - VCAP_SERVICES.xsuaa          → OAuth token for proxy auth
 *
 * No credentials are hardcoded here. The BTP service bindings supply everything.
 */

const cds = require('@sap/cds');
const hana = require('@sap/hana-client');
const SocksProxyAgent = require('socks-proxy-agent').SocksProxyAgent; // for proxy tunnel

// ─────────────────────────────────────────────────────────────────────────────
// SAP serial date → ISO-8601 calendar date
// SAP/CAR stores dates as Excel serial numbers (epoch: 1899-12-30).
// ─────────────────────────────────────────────────────────────────────────────
const SAP_EPOCH_MS = Date.UTC(1899, 11, 30); // Dec 30, 1899 in UTC ms

function sapSerialToISO(serial) {
  const ms = SAP_EPOCH_MS + Math.floor(serial) * 86400000;
  return new Date(ms).toISOString().slice(0, 10);
}

// ─────────────────────────────────────────────────────────────────────────────
// ISO-8601 date → SAP serial (for WHERE clause filters)
// ─────────────────────────────────────────────────────────────────────────────
function isoToSapSerial(isoDate) {
  const d = new Date(isoDate + 'T00:00:00Z');
  return Math.round((d.getTime() - SAP_EPOCH_MS) / 86400000);
}

// ─────────────────────────────────────────────────────────────────────────────
// Resolve the CAR_HANA destination from BTP Destination Service.
// Returns { host, port, user, password } — never logged in full.
// ─────────────────────────────────────────────────────────────────────────────
async function resolveCarHanaDestination() {
  // In BTP CF the Destination Service SDK resolves via VCAP_SERVICES automatically.
  // We read it manually here to keep the dependency footprint small.
  const vcap = JSON.parse(process.env.VCAP_SERVICES || '{}');

  // Destination service credentials
  const destBinding = vcap.destination?.[0]?.credentials;
  if (!destBinding) {
    throw new Error(
      'BTP Destination Service binding not found in VCAP_SERVICES. ' +
      'Bind the destination service to this app in BTP.'
    );
  }

  // Connectivity service credentials (for SOCKS5 proxy + JWT)
  const connBinding = vcap.connectivity?.[0]?.credentials;
  if (!connBinding) {
    throw new Error(
      'BTP Connectivity Service binding not found in VCAP_SERVICES. ' +
      'Bind the connectivity service to this app in BTP.'
    );
  }

  // 1. Get OAuth token to call Destination Service REST API
  const tokenRes = await fetch(destBinding.url + '/oauth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'client_credentials',
      client_id: destBinding.clientid,
      client_secret: destBinding.clientsecret,
    }),
  });
  if (!tokenRes.ok) throw new Error(`Destination token fetch failed: ${tokenRes.status}`);
  const { access_token } = await tokenRes.json();

  // 2. Fetch the CAR_HANA destination definition
  const destName = process.env.CAR_HANA_DESTINATION_NAME || 'CAR_HANA';
  const destRes = await fetch(
    `${destBinding.uri}/destination-configuration/v1/destinations/${destName}`,
    { headers: { Authorization: `Bearer ${access_token}` } }
  );
  if (!destRes.ok) {
    throw new Error(
      `Destination '${destName}' not found (${destRes.status}). ` +
      'Create it in BTP cockpit: Connectivity → Destinations → New Destination, ' +
      'Type=HANA, ProxyType=OnPremise.'
    );
  }

  const dest = await destRes.json();
  const props = dest.destinationConfiguration;

  // 3. Get connectivity proxy JWT (authorises the SOCKS5 tunnel)
  const proxyTokenRes = await fetch(connBinding.token_service_url + '/oauth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'client_credentials',
      client_id: connBinding.clientid,
      client_secret: connBinding.clientsecret,
    }),
  });
  if (!proxyTokenRes.ok) throw new Error(`Connectivity token fetch failed: ${proxyTokenRes.status}`);
  const { access_token: proxyToken } = await proxyTokenRes.json();

  return {
    // HANA target (virtual host defined in Cloud Connector)
    host: props.Host,         // e.g. 'car-hana-virtual'
    port: parseInt(props.Port || '30015', 10),
    user: props.User,
    password: props.Password,

    // BTP Connectivity SOCKS5 proxy (routes traffic through Cloud Connector)
    proxyHost: connBinding.onpremise_proxy_host,
    proxyPort: parseInt(connBinding.onpremise_proxy_port, 10),
    proxyToken: proxyToken,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Open a HANA connection through the BTP connectivity proxy.
//
// @sap/hana-client supports a `proxyOptions` parameter that sets up
// a SOCKS5 tunnel when connecting to on-premise HANA via Cloud Connector.
// ─────────────────────────────────────────────────────────────────────────────
async function openHanaConnection(dest) {
  return new Promise((resolve, reject) => {
    const conn = hana.createConnection();
    conn.connect(
      {
        serverNode: `${dest.host}:${dest.port}`,
        uid: dest.user,
        pwd: dest.password,
        encrypt: false,               // Cloud Connector handles TLS termination
        sslValidateCertificate: false,
        // Route through BTP Connectivity SOCKS5 proxy
        proxyOptions: {
          enabled: true,
          protocol: 'SOCKS5',
          host: dest.proxyHost,
          port: dest.proxyPort,
          // The proxy uses a JWT Bearer token for authorization
          auth: `${dest.proxyToken}:`,  // hana-client expects 'token:' format
        },
      },
      (err) => {
        if (err) return reject(new Error(`HANA connect failed: ${err.message}`));
        resolve(conn);
      }
    );
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Query /DMF/TS_PS for the requested article/store/date scope.
//
// NOTE: The table name uses SAP's naming convention with a leading slash,
// which requires double-quoting in HANA SQL.
// ─────────────────────────────────────────────────────────────────────────────
async function queryTimeSeriesFromHana(conn, { articleIds, storeIds, startSerial, endSerial, granularity }) {
  const serialFrom = startSerial;
  const serialTo   = endSerial;

  // Build parameterised IN clause arrays
  const artPlaceholders = articleIds.map((_, i) => `?`).join(', ');
  const locPlaceholders = storeIds.map((_, i) => `?`).join(', ');

  const sql = `
    SELECT
      PROD_ID,
      LOC_ID,
      TSTFR,
      SUM(UNIT_SALES) AS UNIT_SALES,
      SUM(REVENUE_NET) AS REVENUE_NET
    FROM "/DMF/TS_PS"
    WHERE
      MANDT = '100'
      AND PROD_ID IN (${artPlaceholders})
      AND LOC_ID   IN (${locPlaceholders})
      AND TSTFR >= ?
      AND TSTFR <= ?
      AND TIME_GRAN = ?
      AND UNIT_SALES > 0           -- exclude returns and zero rows
    GROUP BY PROD_ID, LOC_ID, TSTFR
    ORDER BY PROD_ID, LOC_ID, TSTFR
  `;

  const params = [
    ...articleIds,
    ...storeIds,
    serialFrom,
    serialTo,
    granularity || 'D',
  ];

  return new Promise((resolve, reject) => {
    conn.exec(sql, params, (err, rows) => {
      if (err) return reject(new Error(`HANA query failed: ${err.message}`));
      resolve(rows);
    });
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// CDS service handler registration
// ─────────────────────────────────────────────────────────────────────────────
module.exports = cds.service.impl(async function (srv) {

  srv.on('readTimeSeries', async (req) => {
    const { articleIds, storeIds, startDate, endDate, granularity } = req.data;

    if (!articleIds?.length || !storeIds?.length) {
      return req.error(400, 'articleIds and storeIds must be non-empty arrays.');
    }

    const startSerial = isoToSapSerial(startDate);
    const endSerial   = isoToSapSerial(endDate) + 0.99999; // include end-of-day

    let dest, conn;
    try {
      dest = await resolveCarHanaDestination();
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
      rows = await queryTimeSeriesFromHana(conn, {
        articleIds,
        storeIds,
        startSerial,
        endSerial,
        granularity,
      });
    } finally {
      // Always close the connection — pooling is handled by @sap/hana-client
      conn.disconnect();
    }

    // Transform raw HANA rows to the agent-facing shape.
    // Convert SAP serial dates back to ISO-8601 calendar dates.
    return rows.map((row) => ({
      articleId:     row.PROD_ID,
      storeId:       row.LOC_ID,
      date:          sapSerialToISO(row.TSTFR),
      salesQuantity: parseFloat(row.UNIT_SALES ?? 0),
      salesValue:    parseFloat(row.REVENUE_NET ?? 0),
    }));
  });
});
