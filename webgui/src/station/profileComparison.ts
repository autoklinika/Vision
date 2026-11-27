import {librarySections} from '../api/libraryContract';
import type {LibrarySectionName} from '../api/libraryContract';
import type {DraftDocument} from './draftContract';
import type {BasicDeclaration} from './basicContract';

export type Difference=Readonly<{section:LibrarySectionName;path:string;before:string;after:string}>;
const LIMIT=256;
function printable(value:unknown):string {
  if(value===undefined)return '—';
  if(value===null)return 'null';
  if(typeof value==='string')return value;
  return JSON.stringify(value);
}
export function compareProfiles(before:DraftDocument,after:DraftDocument,beforeDeclaration?:BasicDeclaration,afterDeclaration?:BasicDeclaration):{differences:Difference[];truncated:boolean}{
  const differences:Difference[]=[];
  let truncated=false;
  function walk(a:unknown,b:unknown,section:LibrarySectionName,path:string){
    if(Object.is(a,b))return;
    if(differences.length>=LIMIT){truncated=true;return;}
    if(Array.isArray(a)&&Array.isArray(b)){
      for(let i=0;i<Math.max(a.length,b.length)&&!truncated;i++)walk(a[i],b[i],section,path+'['+(i+1)+']');
      return;
    }
    if(a&&b&&typeof a==='object'&&typeof b==='object'&&!Array.isArray(a)&&!Array.isArray(b)){
      const x=a as Record<string,unknown>,y=b as Record<string,unknown>;
      for(const key of [...new Set([...Object.keys(x),...Object.keys(y)])].sort()){
        if(truncated)break;
        walk(x[key],y[key],section,path?path+'.'+key:key);
      }
      return;
    }
    differences.push({section,path,before:printable(a),after:printable(b)});
  }
  for(const section of librarySections){if(truncated)break;walk(before[section],after[section],section,'');}
  if(!truncated){
    walk(beforeDeclaration?.familyLabel,afterDeclaration?.familyLabel,'metadata','declaration.familyLabel');
    walk(beforeDeclaration?.variantLabel,afterDeclaration?.variantLabel,'metadata','declaration.variantLabel');
    walk(beforeDeclaration?.states,afterDeclaration?.states,'geometry','declaration.states');
    walk(beforeDeclaration?.photos,afterDeclaration?.photos,'reference_assets','declaration.photos');
    walk(beforeDeclaration?.inspection,afterDeclaration?.inspection,'inspection_workflows','declaration.inspection');
  }
  return {differences,truncated};
}
