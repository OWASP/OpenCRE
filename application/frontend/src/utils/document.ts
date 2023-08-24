import {
  DOCUMENT_TYPES,
  DOCUMENT_TYPE_NAMES,
  TYPE_IS_PART_OF,
  TYPE_LINKED_FROM,
  TYPE_LINKED_TO,
} from '../const';
import { Document, LinkedDocument } from '../types';

export const getDocumentDisplayName = (document: Document) => {
  // [document.doctype, document.id, document.name, document.section, document.subsection].filter(Boolean).join(' - '); // format: Standard - ASVS - V1.1
  if (!document) {
    return '';
  }
  return [
    document.doctype,
    document.id,
    document.name,
    document.version,
    document.sectionID,
    document.section,
    document.subsection,
  ]
    .filter(Boolean)
    .join(' : '); // format: ASVS : V1.1
};
export type LinksByType = Record<string, LinkedDocument[]>;

export const groupLinksByType = (node: Document): LinksByType =>
  node.links ? groupBy(node.links, (link) => link.ltype) : {};

export const orderLinksByType = (lbt: LinksByType): LinksByType => {
  const order = ['Contains', 'Linked To', 'SAME', 'SAM', 'Is Part Of', 'Related'];
  const res: LinksByType = {};
  for (const itm of order) {
    if (lbt[itm]) {
      res[itm] = lbt[itm];
    }
  }
  return res;
};
export const groupBy = <T, K extends keyof any>(list: T[], getKey: (item: T) => K) =>
  list.reduce((previous, currentItem) => {
    const group = getKey(currentItem);
    if (!previous[group]) previous[group] = [];
    previous[group].push(currentItem);
    return previous;
  }, {} as Record<K, T[]>);

export const getInternalUrl = (doc: Document): String => {
  if (doc.doctype.toLowerCase() != 'cre') {
    var standardAPIPath = `/node/${doc.doctype.toLowerCase()}/${doc.name}/`;
    if (doc) {
      if (doc.section) {
        standardAPIPath += `section/${encodeURIComponent(doc.section)}`;
      } else if (doc.sectionID) {
        standardAPIPath += `sectionid/${encodeURIComponent(doc.sectionID)}`;
      }
    }
    return standardAPIPath;
  }
  return `/cre/${doc.id}`;
};

export const getApiEndpoint = (doc: Document, apiUrl: string): string => {
  if (doc.doctype.toLowerCase() != 'cre') {
    var standardAPIPath = `${apiUrl}/${doc.doctype.toLowerCase()}/${doc.name}`;
    if (doc) {
      if (doc.section) {
        standardAPIPath += `section/${encodeURIComponent(doc.section)}`;
      } else if (doc.sectionID) {
        standardAPIPath += `sectionid/${encodeURIComponent(doc.sectionID)}`;
      }
      return standardAPIPath;
    }
    return standardAPIPath;
  }

  return `${apiUrl}/id/${doc.id}`;
};

export const getDocumentTypeText = (linkType, docType, parentDocType = ''): string => {
  let docText = DOCUMENT_TYPE_NAMES[linkType];
  if (linkType === TYPE_LINKED_TO && docType === DOCUMENT_TYPES.TYPE_CRE) {
    docText =
      parentDocType === DOCUMENT_TYPES.TYPE_STANDARD
        ? DOCUMENT_TYPE_NAMES[TYPE_LINKED_FROM]
        : DOCUMENT_TYPE_NAMES[TYPE_IS_PART_OF];
  }
  return docText;
};
