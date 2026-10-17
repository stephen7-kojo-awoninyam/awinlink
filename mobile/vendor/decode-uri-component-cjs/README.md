# CommonJS compatibility adapter

Source: `decode-uri-component@0.5.0`, from the npm registry tarball (SHA-1 `4592fa1e1d640ec5e2760e2e168ad2ab5f2c9da1`). The upstream MIT license is preserved in LICENSE.

This vendors the upstream iterative UTF-8 decoder fixing GHSA-vcc3-ghjq-m6fr. Changes are limited to exporting the function with CommonJS and preserving the old decoder's literal-plus-to-space behavior. It replaces query-string's recursive 0.2.x decoder without changing Expo Router or the query-string API. query-string also handles plus normalization itself.

Remove this adapter when Expo Router uses a compatible patched decoder. Regression tests exercise malformed escapes, Unicode, deep invalid input, and the actual query-string consumer.
