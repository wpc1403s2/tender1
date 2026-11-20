import type { SourceReference } from './tender';

export interface ComponentCategoryOption {
  code: string;
  label: string;
  field_prefix: string;
}

export interface ComponentLibraryItem {
  comp_id: string;
  component_category: string;
  category_label: string;
  manufacturer: string;
  model_series: string;
  key_metrics: Record<string, any>;
  specs_json: Record<string, any>;
  summary_text: string;
  catalog_ref?: SourceReference | null;
  created_at?: string;
}
