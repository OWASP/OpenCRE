import { Document, LinkedDocument } from '../types';

export const getDocumentDisplayName = (document: Document) =>
  [document.id, document.name, document.section, document.subsection].filter(Boolean).join(' - ');

export type LinksByType = Record<string, LinkedDocument[]>;
export const getLinksByType = (node: Document): LinksByType =>
  node.links
    ? node.links.reduce<LinksByType>((acc: LinksByType, val: LinkedDocument) => {
        if (!acc[val.type]) {
          acc[val.type] = [];
        }
        acc[val.type].push(val);
        return acc;
      }, {})
    : {};
