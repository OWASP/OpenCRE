export interface Document {
  doctype: string;
  name: string;
  // For documents with children
  links?: LinkedDocument[];
  // For CREs
  description?: string;
  id?: string;
  // For Standards
  hyperlink?: string;
  section?: string;
  subsection?: string;
}
export interface LinkedDocument {
  document: Document;
  type: string;
}

export enum LinkTypes{
  "SAME" = 1,
  "LinkedTo",
  "Is Part Of",
  "Contains",
  "Related",
}