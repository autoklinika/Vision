import {expect,it} from 'vitest';
import {emptyDeclaration,isBasicDeclaration,validIdentityLabel} from '../src/station/basicContract';
import {compareProfiles} from '../src/station/profileComparison';
import type {DraftDocument} from '../src/station/draftContract';

it('accepts human labels and incomplete declared dimensions, not invented measurements',()=>{
 const d=emptyDeclaration('Delphi Truck','285');
 d.states=[{stateId:'pcb_top',dimensionsMm:[100.25,null,20]}];
 d.inspection.notes='First line\nSecond line';
 expect(validIdentityLabel('Delphi Truck')).toBe(true);
 expect(validIdentityLabel('bad/label')).toBe(false);
 expect(isBasicDeclaration(d)).toBe(true);
 expect(isBasicDeclaration({...d,states:[{stateId:'pcb_top',dimensionsMm:[0,null,20]}]})).toBe(false);
 expect(isBasicDeclaration({...d,inspection:{...d.inspection,template:'anything'}})).toBe(false);
 expect(isBasicDeclaration({...d,approved:true})).toBe(false);
});
it('detects actual raw dimensions in history comparisons',()=>{
 const a=emptyDeclaration('Test','285');a.states=[{stateId:'closed',dimensionsMm:[null,80,20]}];
 const b=structuredClone(a);b.states[0].dimensionsMm[0]=101;
 const same={} as DraftDocument;
 expect(compareProfiles(same,same,a,b).differences).toEqual([{section:'geometry',path:'declaration.states[1].dimensionsMm[1]',before:'null',after:'101'}]);
});
