import { Document, LinkedDocument } from '../types';

export const getDocumentDisplayName = (document: Document) =>
  [document.id, document.name, document.section, document.subsection].filter(Boolean).join(' - ');

export type LinksByType = Record<string, LinkedDocument[]>;

export const groupLinksByType = (node: Document): LinksByType =>
  node.links
    ? groupBy(node.links, link => link.type)
    : {};

export const groupBy = <T, K extends keyof any>(list: T[], getKey: (item: T) => K) =>
  list.reduce((previous, currentItem) => {
    const group = getKey(currentItem);
    if (!previous[group]) previous[group] = [];
    previous[group].push(currentItem);
    return previous;
}, {} as Record<K, T[]>);

export const getInternalUrl = (doc: Document): String => {
  if (doc.doctype === 'Standard') {
    var standardAPIPath = `/standard/${doc.name}/`;
    if ( doc && doc.section){
      standardAPIPath += `section/${encodeURIComponent(doc.section)}`;
    }
    return standardAPIPath
  }

  return `/cre/${doc.id}`
}

export const getApiEndpoint = (doc: Document, apiUrl: string): string => {
  if (doc.doctype === 'Standard') {
    var standardAPIPath = `${apiUrl}/standard/${doc.name}`;
    if ( doc && doc.section){
      standardAPIPath += `?section=${encodeURIComponent(doc.section)}`;
    }
    return standardAPIPath
  }
  
  return `${apiUrl}/id/${doc.id}`
}