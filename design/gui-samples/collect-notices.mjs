import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const groups = new Map();
const seen = new Set();
function visitModules(directory) {
  if (!fs.existsSync(directory)) return;
  for (const entry of fs.readdirSync(directory, {withFileTypes:true})) {
    if (!entry.isDirectory() || entry.name.startsWith('.')) continue;
    const full = path.join(directory,entry.name);
    if (entry.name.startsWith('@')) {
      for (const nested of fs.readdirSync(full,{withFileTypes:true}))
        if(nested.isDirectory()) visitPackage(path.join(full,nested.name));
    } else visitPackage(full);
  }
}
function visitPackage(directory) {
  const file = path.join(directory,'package.json');
  if (!fs.existsSync(file) || seen.has(directory)) return;
  seen.add(directory);
  const info = JSON.parse(fs.readFileSync(file,'utf8'));
  const licenses = fs.readdirSync(directory).filter(name=>/^(licen[sc]e|copying|notice)(\.|$)/i.test(name));
  for (const license of licenses) {
    const source = path.join(directory,license);
    if (!fs.statSync(source).isFile()) continue;
    const body = fs.readFileSync(source,'utf8');
    const digest = crypto.createHash('sha256').update(body).digest('hex');
    const group = groups.get(digest) ?? {packages:[],body};
    group.packages.push(info.name+'@'+info.version+' / '+license);
    groups.set(digest,group);
  }
  visitModules(path.join(directory,'node_modules'));
}
visitModules('node_modules');
const content = 'Third-party notices for the isolated Vision GUI sample build.\nIncludes dependencies used to build these samples.\n\n'+[...groups.values()].map(group=>group.packages.sort().join('\n')+'\n\n'+group.body).join('\n\n'+'='.repeat(70)+'\n\n');
fs.writeFileSync('dist/THIRD_PARTY_NOTICES.txt',content);
console.log('Third-party notices collected: '+groups.size+' distinct license/notice texts.');
