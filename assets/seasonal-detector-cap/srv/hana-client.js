'use strict';

/**
 * Shared HANA connectivity helpers for on-premise CAR HANA access
 * via BTP Connectivity Service + Cloud Connector.
 *
 * No credentials are stored here. Everything is resolved at runtime:
 *   - HANA host/port/user/password  → BTP Destination (name from env CAR_HANA_DESTINATION_NAME)
 *   - SOCKS5 proxy details          → BTP Connectivity Service VCAP binding
 *   - Proxy JWT                     → Connectivity token endpoint
 */

const hana = require('@sap/hana-client');

/**
 * Resolves a named BTP Destination and the Connectivity proxy details.
 * @param {string} [destinationName] - Override the destination name (default: env CAR_HANA_DESTINATION_NAME or 'CAR_HANA')
 * @returns {{ host, port, user, password, proxyHost, proxyPort, proxyToken }}
 */
async function resolveHanaDestination(destinationName) {
  const vcap = JSON.parse(process.env.VCAP_SERVICES || '{}');

  const destBinding = vcap.destination?.[0]?.credentials;
  if (!destBinding) {
    throw new Error(
      'BTP Destination Service binding not found in VCAP_SERVICES. ' +
      'Bind the destination service to this CF app.'
    );
  }

  const connBinding = vcap.connectivity?.[0]?.credentials;
  if (!connBinding) {
    throw new Error(
      'BTP Connectivity Service binding not found in VCAP_SERVICES. ' +
      'Bind the connectivity service to this CF app.'
    );
  }

  // Fetch OAuth token to call Destination Service REST API
  const tokenRes = await fetch(`${destBinding.url}/oauth/token`, {
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

  const destName = destinationName || process.env.CAR_HANA_DESTINATION_NAME || 'CAR_HANA';
  const destRes = await fetch(
    `${destBinding.uri}/destination-configuration/v1/destinations/${destName}`,
    { headers: { Authorization: `Bearer ${access_token}` } }
  );
  if (!destRes.ok) {
    throw new Error(
      `BTP Destination '${destName}' not found (${destRes.status}). ` +
      'Create it in BTP cockpit: Connectivity → Destinations → New Destination, ' +
      'Type=HANA, ProxyType=OnPremise, Host=<virtual-host>, Port=30015.'
    );
  }
  const dest = await destRes.json();
  const props = dest.destinationConfiguration;

  // Fetch connectivity proxy JWT (authorises the SOCKS5 tunnel)
  const proxyTokenRes = await fetch(`${connBinding.token_service_url}/oauth/token`, {
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
    host:       props.Host,
    port:       parseInt(props.Port || '30015', 10),
    user:       props.User,
    password:   props.Password,
    proxyHost:  connBinding.onpremise_proxy_host,
    proxyPort:  parseInt(connBinding.onpremise_proxy_port, 10),
    proxyToken,
  };
}

/**
 * Opens a @sap/hana-client connection routed through the BTP SOCKS5 proxy.
 * Caller is responsible for calling conn.disconnect() when done.
 */
async function openHanaConnection(dest) {
  return new Promise((resolve, reject) => {
    const conn = hana.createConnection();
    conn.connect(
      {
        serverNode:            `${dest.host}:${dest.port}`,
        uid:                   dest.user,
        pwd:                   dest.password,
        encrypt:               false,
        sslValidateCertificate: false,
        proxyOptions: {
          enabled:  true,
          protocol: 'SOCKS5',
          host:     dest.proxyHost,
          port:     dest.proxyPort,
          auth:     `${dest.proxyToken}:`,
        },
      },
      (err) => {
        if (err) return reject(new Error(`HANA connect failed: ${err.message}`));
        resolve(conn);
      }
    );
  });
}

/**
 * Convenience: resolve destination + open connection in one call.
 * @param {string} [destinationName]
 */
async function connect(destinationName) {
  const dest = await resolveHanaDestination(destinationName);
  const conn = await openHanaConnection(dest);
  return conn;
}

/** Promisified conn.exec for SELECT/DML statements. */
function execSql(conn, sql, params = []) {
  return new Promise((resolve, reject) => {
    conn.exec(sql, params, (err, rows) => {
      if (err) return reject(new Error(`HANA SQL failed: ${err.message}\nSQL: ${sql.trim().split('\n')[0]}`));
      resolve(rows);
    });
  });
}

module.exports = { resolveHanaDestination, openHanaConnection, connect, execSql };
