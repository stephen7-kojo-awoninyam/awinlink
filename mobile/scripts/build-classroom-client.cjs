const { readFileSync, writeFileSync } = require('node:fs');
const { resolve } = require('node:path');
const source = resolve(__dirname, '../src/classrooms/client.js');
const target = resolve(__dirname, '../../static/js/classroom-client.js');
writeFileSync(target, readFileSync(source));
console.log('Updated shared browser classroom controller.');
