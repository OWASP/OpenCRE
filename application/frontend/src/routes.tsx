import { ReactNode } from 'react';

import { CommonRequirementEnumeration, Graph, Search, Standard } from './pages';
import { SearchName } from './pages/Search/SearchName';
import { StandardSection } from './pages/Standard/StandardSection';

import {Deeplink} from './pages/Deeplink/Deeplink';
export interface IRoute {
  path: string;
  component: ReactNode | ReactNode[];
  showHeader: boolean;
}

import {
  INDEX, STANDARD, SECTION, CRE, GRAPH, SEARCH, DEEPLINK,
} from './const';

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
  {
    path: `${DEEPLINK}/:standardName`,
    component: Deeplink,
    showHeader: true,
  }
];
