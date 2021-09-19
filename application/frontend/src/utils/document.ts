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
