import { createContext } from 'react';

import { DocumentNode } from '../components/DocumentNode';
import { Document, LinkedDocument } from '../types';

const filterLinks = (document: Document, filters: string[]): Document | undefined => {
  // TODO(spyros): this can be merged with the one below and avoid code duplication
  // let identifier = document.doctype == "CRE" ? "c:" + document.id : "s:" + document.name
  let identifier = document.doctype == 'CRE' ? '' + document.id : '' + document.name;
  let links: LinkedDocument[] = [];
  document?.links?.forEach((link) => {
    const newDoc: Document | undefined = filterLinks(link.document, filters);
    if (newDoc) {
      const ldoc: LinkedDocument = { document: newDoc, ltype: link.ltype };
      links.push(ldoc);
    }
  });
  if (links.length > 0 || filters?.includes(identifier.toLowerCase()) || document.doctype == 'CRE') {
    return {
      doctype: document.doctype,
      name: document.name,
      description: document.description,
      hyperlink: document.hyperlink,
      id: document.id,
      section: document.section,
      subsection: document.subsection,
      tags: document.tags,
      links: links,
    };
  }
};
export const applyFilters = (node: Document): Document => {
  // Given an array of document nodes and having a list of filters in the URL, return only the nodes and links that satisfy the filter conditions
  const nodes = node?.links || [];
  var filteredNodes: LinkedDocument[] = [];
  let currentUrlParams = new URLSearchParams(window.location.search);
  let doFilter = currentUrlParams.get('applyFilters') == 'true' ? true : false;
  if (!currentUrlParams.has('filters') || !doFilter) {
    return node;
  }
  let filters = currentUrlParams.getAll('filters').map((v) => v.toLowerCase());
  nodes.forEach((node) => {
    const newNode = filterLinks(node.document, filters);
    if (newNode) {
      const newDocNode: LinkedDocument = { document: newNode, ltype: node.ltype };
      filteredNodes.push(newDocNode);
    }
  });
  node.links = filteredNodes;
  return node;
};

export const GlobalFilterState = {
  // TODO (spyros): when there's a clean solution to getting recursive documentNodes use this to store filtered and default document
  savedDoc: new Document(),
  workingDoc: new Document(),
};

export const filterContext = createContext(GlobalFilterState);
