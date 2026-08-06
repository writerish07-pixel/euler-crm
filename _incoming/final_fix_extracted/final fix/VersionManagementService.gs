/**
 * VersionManagementService – LTS version tracking for logs and deployment.
 */

var VERSION_KEYS = {
  DEPLOYMENT_DATE: 'crm_deployment_date',
  DEPLOYMENT_CERTIFIED: 'crm_deployment_certified',
  DEPLOYMENT_CERT_DATE: 'crm_deployment_cert_date'
};

/** Compact version string attached to every log entry. */
function getVersionTag_() {
  var info = getVersionInfo_();
  return info.crmVersion + '+' + (info.patchVersion || '') + '|sch:' + info.schemaVersion + '|mig:' + info.migrationVersion;
}

/** Full version record. */
function getVersionInfo_() {
  var props = PropertiesService.getScriptProperties();
  return {
    crmVersion: CRM.VERSION,
    patchVersion: CRM.PATCH_VERSION || '',
    schemaVersion: CRM.SCHEMA_VERSION,
    migrationVersion: CRM.MIGRATION_VERSION,
    appsScriptBuild: CRM.APPS_SCRIPT_BUILD,
    deploymentDate: props.getProperty(VERSION_KEYS.DEPLOYMENT_DATE) || '',
    deploymentCertified: props.getProperty(VERSION_KEYS.DEPLOYMENT_CERTIFIED) === '1',
    deploymentCertDate: props.getProperty(VERSION_KEYS.DEPLOYMENT_CERT_DATE) || '',
    spreadsheetId: getSpreadsheet_().getId()
  };
}

function recordDeployment_() {
  var now = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss');
  var props = PropertiesService.getScriptProperties();
  props.setProperty(VERSION_KEYS.DEPLOYMENT_DATE, now);
  props.setProperty(VERSION_KEYS.DEPLOYMENT_CERTIFIED, '1');
  props.setProperty(VERSION_KEYS.DEPLOYMENT_CERT_DATE, now);
  logAudit_('DEPLOYMENT_RECORDED', 'LTS deployment locked at ' + now + ' [' + getVersionTag_() + ']');
}

function isDeploymentCertified_() {
  return PropertiesService.getScriptProperties().getProperty(VERSION_KEYS.DEPLOYMENT_CERTIFIED) === '1';
}

function clearDeploymentCertification_() {
  var props = PropertiesService.getScriptProperties();
  props.deleteProperty(VERSION_KEYS.DEPLOYMENT_CERTIFIED);
  props.deleteProperty(VERSION_KEYS.DEPLOYMENT_CERT_DATE);
}
