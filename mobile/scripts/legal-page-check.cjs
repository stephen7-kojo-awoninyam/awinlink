// A reachable draft or incomplete contact page is not a store-ready policy.
function assertLegalPageReady(body) {
  if (!body.includes('Awinlink')) throw new Error('Public page must identify Awinlink');
  if (/data-legal-status\s*=\s*["']draft["']|Draft for legal review/i.test(body)) {
    throw new Error('Legal pages remain drafts and require operator/legal approval');
  }
  if (body.includes('Release information is awaiting completion') || /contact has not yet been configured|support email has not yet been configured/i.test(body)) {
    throw new Error('Operator/contact configuration is incomplete');
  }
}
module.exports = { assertLegalPageReady };
