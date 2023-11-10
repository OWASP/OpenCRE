export interface Document {
  doctype: string;
  name: string;
  // For documents with children
  links?: LinkedDocument[];
  // For CREs
  description?: string;
  id: string;
  // For Standards
  hyperlink?: string;
  section?: string;
  subsection?: string;
  tags?: string[];
  tooltype?: string;
  sectionID?: string;
  version?: string;
}
export interface LinkedDocument {
  document: Document;
  ltype: string;
}

interface GapAnalysisPathSegment {
  start: Document;
  end: Document;
  relationship: string;
  score: number;
}

interface GapAnalysisPath {
  end: Document;
  path: GapAnalysisPathSegment[];
}

export interface GapAnalysisPathStart {
  start: Document;
  paths: Record<string, GapAnalysisPath>;
  extra: number;
  weakLinks: Record<string, GapAnalysisPath>;
}

export interface TreeDocument extends Document {
  displayName: string;
  url: string;
  links: LinkedTreeDocument[];
}

export interface LinkedTreeDocument {
  document: TreeDocument;
  ltype: string;
}

export interface PaginatedResponse {
  standards: Document[];
  total_pages: number;
}
