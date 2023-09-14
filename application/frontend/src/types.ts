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
}

interface GapAnalysisPath {
  end: Document;
  path: GapAnalysisPathSegment[];
}

export interface GapAnalysisPathStart {
  start: Document;
  paths: Record<string, GapAnalysisPath>;
}
