export const TWO_DAYS_MILLISECONDS = 1.728e8;

export const TYPE_IS_PART_OF = 'Is Part Of';
export const TYPE_LINKED_TO = 'Linked To';
export const TYPE_LINKED_FROM = 'Linked From';
export const TYPE_CONTAINS = 'Contains';
export const TYPE_RELATED = 'Related';
export const TYPE_SAME = 'SAME';
export const TYPE_SAM = 'SAM';

export const DOCUMENT_TYPE_NAMES = {
  [TYPE_SAME]: ' has been automatically mapped to',
  [TYPE_SAM]: ' has been automatically mapped to',
  [TYPE_LINKED_TO]: ' is linked to sources',
  [TYPE_IS_PART_OF]: ' is part of CREs',
  [TYPE_LINKED_FROM]: 'is linked from CREs',
  [TYPE_CONTAINS]: ' contains CREs',
  [TYPE_RELATED]: ' is related to CREs',
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
export const BROWSEROOT = '/root_cres';
export const GAP_ANALYSIS = '/map_analysis';
export const EXPLORER = '/explorer';

export const GA_STRONG_UPPER_LIMIT = 2; // remember to change this in the Python code too
