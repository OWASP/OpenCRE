export const TYPE_IS_PART_OF = 'Is Part Of';
export const TYPE_LINKED_TO = 'Linked To';
export const TYPE_CONTAINS = 'Contains';
export const TYPE_RELATED = 'Related';
export const TYPE_SAME = 'SAME';
export const TYPE_SAM = 'SAM';

export const DOCUMENT_TYPE_NAMES = {
  [TYPE_SAME]: 'is the same as',
  [TYPE_SAM]: 'is the same as',
  [TYPE_LINKED_TO]: 'is linked to',
  [TYPE_IS_PART_OF]: 'is part of',
  [TYPE_CONTAINS]: 'contains',
  [TYPE_RELATED]: 'is related to',
};

export const DOCUMENT_TYPES = {
  TYPE_TOOL: 'Tool',
  TYPE_CRE: 'CRE',
  TYPE_STANDARD: 'Standard',
  TYPE_CODE: 'Code',
};

// Routes
export const INDEX = '/';
export const STANDARD = '/standard';
export const TOOL = '/tool';
export const CODE = '/code';
export const SECTION = '/section';
export const SECTION_ID = '/sectionID';
export const SUBSECTION = '/subsection';
export const SEARCH = '/search';
export const CRE = '/cre';
export const GRAPH = '/graph';
export const DEEPLINK = '/deeplink';
export const BROWSEROOT = '/root_cres';
