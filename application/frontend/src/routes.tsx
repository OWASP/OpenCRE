import { ReactNode } from 'react';

import { CommonRequirementEnumeration, Graph, Search, Standard } from './pages';
import { SearchName } from './pages/Search/SearchName';
import { StandardSection } from './pages/Standard/StandardSection';

export interface IRoute {
  // The url to this route
  path: string;
  // What component(s) this will render
  component: ReactNode | ReactNode[];
  // Whether to show the header on this route
  showHeader: boolean;
}

export const INDEX = '/';
export const STANDARD = '/standard';
export const SECTION = '/section';
export const SEARCH = '/search';
export const CRE = '/cre';
export const GRAPH = '/graph';

export const ROUTES: IRoute[] = [
  {
    path: INDEX,
    component: Search,
    showHeader: false,
  },
  {
    path: `${STANDARD}/:id${SECTION}/:section`,
    component: StandardSection,
    showHeader: true,
  },
  {
    path: `${STANDARD}/:id`,
    component: Standard,
    showHeader: true,
  },
  {
    path: `${CRE}/:id`,
    component: CommonRequirementEnumeration,
    showHeader: true,
  },
  {
    path: `${GRAPH}/:id`,
    component: Graph,
    showHeader: true,
  },
  {
    path: `${SEARCH}/:searchTerm`,
    component: SearchName,
    showHeader: true,
  },
];
