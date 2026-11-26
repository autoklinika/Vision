import console from "node:console";
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

// Preserve the existing attribution, including the legacy font licenses.
const existing = fs.readFileSync('public/THIRD_PARTY_NOTICES.txt', 'utf8');
const { packages } = JSON.parse(fs.readFileSync('package-lock.json', 'utf8'));
const groups = new Map();
for (const [directory, metadata] of Object.entries(packages)) {
  if (!directory.startsWith('node_modules/') || metadata.dev) continue;
  if (!fs.existsSync(directory)) {
    if (metadata.optional) continue;
    throw new Error('Missing production dependency: ' + directory);
  }
  const info = JSON.parse(fs.readFileSync(path.join(directory, 'package.json'), 'utf8'));
  for (const file of fs.readdirSync(directory).filter(name => /^(licen[sc]e|copying|notice)(\.|$)/i.test(name)).sort()) {
    const source = path.join(directory, file);
    if (!fs.statSync(source).isFile()) continue;
    const body = fs.readFileSync(source, 'utf8');
    const digest = crypto.createHash('sha256').update(body).digest('hex');
    const group = groups.get(digest) ?? { packages: [], body };
    group.packages.push(info.name + '@' + info.version + ' / ' + file);
    groups.set(digest, group);
  }
}
const additions = [...groups.values()].map(group => group.packages.sort().join('\n') + '\n\n' + group.body).join('\n\n' + '='.repeat(70) + '\n\n');
fs.writeFileSync('dist/THIRD_PARTY_NOTICES.txt', existing + '\n\nProduction dependency notices\n\n' + additions + '\n');
console.log('Third-party notices collected: ' + groups.size + ' distinct license/notice texts.');
