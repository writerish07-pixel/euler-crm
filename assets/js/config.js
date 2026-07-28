/**
 * Portal runtime config — swap API_BASE_URL when moving to FastAPI later.
 * Frontend never knows about spreadsheets.
 */
window.CRM_CONFIG = {
  APP_NAME: 'Euler Motors CRM',
  APP_TAGLINE: 'Dealer Management Portal',
  /** Deployed Apps Script Web App URL (ends with /exec). Leave blank to use mock/demo mode. */
  API_BASE_URL: 'https://script.google.com/macros/s/AKfycbxHLciADCZ8FpVst4_ypZYeJKGtMn5Dq0WcSXOz1NdaKH8C9gjUVvSkp6Chmsdhx6Y7Sw/exec',
  /**
   * IMPORTANT
   * This URL must be a Web App deployment that includes WebApi.gs (doGet / doPost).
   * If Apps Script returns "Script function not found: doGet", paste WebApi.gs and
   * Deploy → Manage deployments → Edit → New version (or New deployment).
   * Access: Execute as Me · Who has access: Anyone (anonymous) for browser fetch.
   * Do not open the portal via file:// — use a local server (see README).
   */
  /** When true and API_BASE_URL empty, UI shows demo empty states instead of failing hard. */
  ALLOW_DEMO: true,
    REQUEST_TIMEOUT_MS: 90000,
  THEME_KEY: 'euler_crm_theme'
};
