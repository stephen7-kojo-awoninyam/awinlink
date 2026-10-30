# High-severity mobile dependency remediation

Implemented locally on 2026-10-28. No deployment, publishing, native build, credential access or production configuration change.

## Audit and fixes

The five high-severity entries in the production dependency audit came from two underlying dependencies. The remaining three entries propagated through Expo's dependency chain; they were not five independent application defects.

| Previously high entry | Cause | Local remediation |
| --- | --- | --- |
| node-forge | GHSA-86w9-cpqp-85rv: malformed nested DigestAlgorithm data accepted during RSA verification | Pin the transitive dependency to 1.4.2 via an npm override. The installed verifier enforces canonical DER; regression coverage verifies malformed nested elements are rejected while valid Expo code signatures still work. |
| zod | GHSA-mrhx-c7xc-m3w5: memory exhaustion during collection validation | Override Expo CLI's Zod dependency to patched 4.6.7. Expo CLI 57.0.31 requested Zod 3.25.76; its actual plugin/command schema consumers were inspected and tested against Zod 4. |
| @expo/cli | Inherited affected dependencies | Cleared by the two overrides; CLI version unchanged. |
| expo | Inherited affected CLI | High finding cleared; Expo version unchanged. |
| @config-plugins/react-native-webrtc | Inherited affected Expo peer | High finding cleared; plugin and native WebRTC versions unchanged. |

Changes are confined to package overrides, the npm lockfile and regression fixtures/tests. npm installation used `--ignore-scripts --no-audit --no-fund`; no lifecycle scripts or forced audit fixes ran. The lockfile changes two package versions and deduplicates three already-patched Zod copies. Existing overrides and the local URI decoder are preserved.

The installed framework versions remain:

| Package | Before and after |
| --- | --- |
| expo | 57.0.30 |
| @expo/cli | 57.0.31 |
| react | 19.2.3 |
| react-native | 0.86.3 |
| react-native-webrtc | 124.0.8 |
| @config-plugins/react-native-webrtc | 15.0.2 |

The Zod override crosses a dependency major version, so compatibility is explicitly checked rather than assumed: actual Expo plugin descriptors, output validation, command schemas, strict unknown-field rejection and JSON Schema conversion pass. EAS profile/schema tests also pass. Revisit the scoped override when upgrading Expo CLI; do not remove these checks merely to accept a newer dependency graph.

## Security and compatibility verification

- All seven dependency checks passed, including valid Expo certificate/signature handling, rejection of malformed nested DigestAlgorithm elements using ephemeral fixture keys, and bounded error collection for oversized constrained arrays.
- Updated the native call test fixture to provide valid synthetic TURN settings, use the real ICE validator and define React Native's production `__DEV__` global. The previous fixture supplied no TURN in relay-only mode and omitted that global. Added tests for fail-closed relay-only startup and successful direct-call startup under policy all. Application ICE/privacy behavior was not weakened.
- Full `npm test`: **196 tests, 193 passed, three browser-dependent skips, zero failures**. This includes cancellation, permission-race cleanup, canonical signaling, WebRTC media, classroom, native call plugin, release configuration and existing dependency compatibility checks.
- `npm run typecheck`: passed (`tsc --noEmit`).
- `npm ls` for Expo, React Native, WebRTC, its plugin, Zod and node-forge: passed without invalid dependency relationships.
- Actual Expo CLI `--version` and `export --help` passed with offline mode/telemetry disabled.
- Targeted diff whitespace checks passed.

Fresh registry audits after installation:

| Scope | High | Critical | Other remaining entries |
| --- | --- | --- | --- |
| Production (`npm audit --omit=dev`) | 0 | 0 | Eight low |
| Full dependency tree (`npm audit`) | 0 | 0 | Six moderate, nine low |

The production baseline had five high and five low entries. Audit package counts include inherited findings and may change classification as a higher-severity underlying dependency is removed. The tree is not vulnerability-free; lower-severity findings remain outside this high-severity remediation. npm audit exits nonzero for these remaining findings, not because a high finding remains.

Ignored evidence: `.audit-production-readiness/dependencies-after-production.json`, `.audit-production-readiness/dependencies-after-all.json`; test/typecheck logs: `.audit-dependency-tests-verified.log`, `.audit-dependency-typecheck.log`. These checks do not prove device-level native call operation or a successful Android/iOS build. No real calls, updates or builds were sent to external services.

## References

- [Zod advisory](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5) and [Zod releases](https://github.com/colinhacks/zod/releases) identify the patched 4.6.6+ line; 4.6.7 is installed.
- [node-forge advisory](https://github.com/advisories/GHSA-86w9-cpqp-85rv) documents the nested signature-verification issue. The advisory page still listed no patch when read, while npm supplied 1.4.2 and its current advisory query no longer flags that version. The installed canonical-DER behavior is independently exercised by the regression test; remediation does not rely solely on the advisory page's patch metadata.
