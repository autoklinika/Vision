export type Variant = 'carbon' | 'fluent';
export type Draft = { name: string; family: string; variantId: string; profileId: string; revision: string };
export type FieldName = keyof Draft;
export type Errors = Partial<Record<FieldName, string>>;
export interface EditorProps {
  draft: Draft;
  errors: Errors;
  created: boolean;
  dirty: boolean;
  notice: string;
  onChange: (field: FieldName, value: string) => void;
  onSubmit: () => void;
  onReset: () => void;
}
export const emptyDraft: Draft = {name: '', family: '', variantId: '', profileId: '', revision: 'r1'};
export const fieldOrder: FieldName[] = ['name', 'family', 'variantId', 'profileId', 'revision'];
export const fields: Record<FieldName, {label: string; hint: string; maxLength: number}> = {
  name: {label: 'Nazwa profilu', hint: 'Nazwa widoczna na liście profili ECU.', maxLength: 160},
  family: {label: 'Rodzina ECU', hint: 'Rodzina lub model sterownika.', maxLength: 64},
  variantId: {label: 'Wariant', hint: 'Oznaczenie wersji w obrębie rodziny.', maxLength: 64},
  profileId: {label: 'Identyfikator profilu', hint: 'Jednoznaczne oznaczenie profilu w bibliotece.', maxLength: 64},
  revision: {label: 'Rewizja', hint: 'Wersja definicji profilu.', maxLength: 64},
};
