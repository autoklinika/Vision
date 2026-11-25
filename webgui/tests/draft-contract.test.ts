import {describe,expect,it} from 'vitest';
import {identifier,referenceIdentifier,isDraftAssetPreview} from '../src/station/draftContract';

const preview=(assetId:string)=>({
  schema:'vision.api.ecu-draft-asset.v1',source:'STATION',instanceId:'a'.repeat(32),key:'profile',
  sha256:'b'.repeat(64),relativePath:'assets/'+'b'.repeat(64),bytes:3,mime:'image/png',
  status:'UNVERIFIED',assetId,data:'YWJj',
});
describe('reference asset identifier contract',()=>{
  it('accepts preview IDs with dots and the full V1 length without loosening storage keys',()=>{
    for(const id of ['photo.test','photo.'+'x'.repeat(122)]) {
      expect(referenceIdentifier(id)).toBe(true);
      expect(isDraftAssetPreview(preview(id))).toBe(true);
      expect(identifier(id)).toBe(false);
      expect(isDraftAssetPreview({...preview(id),key:id})).toBe(false);
    }
  });
  it('rejects paths, control characters and IDs outside the reference schema',()=>{
    for(const id of ['', '../photo', 'photo/test', '.photo', 'x'.repeat(129), 'photo.test\n', 'photo\0test', 'zdjęcie']) {
      expect(referenceIdentifier(id)).toBe(false);
      expect(isDraftAssetPreview(preview(id))).toBe(false);
    }
  });
});
