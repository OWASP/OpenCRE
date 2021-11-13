import { Component, ReactNode } from 'react';

import { CommonRequirementEnumeration, Graph, Search, Standard } from './pages';
import { SearchName } from './pages/Search/SearchName';
import { StandardSection } from './pages/Standard/StandardSection';
import {Deeplink} from './pages/Deeplink/Deeplink';
export interface IRoute {
  path: string;
  component: ReactNode | ReactNode[];
  showHeader: boolean;
  showFilter: boolean;
}

import {
  INDEX, STANDARD, SECTION, CRE, GRAPH, SEARCH, DEEPLINK,
} from './const';

export const ROUTES: IRoute[] = [
  {
    path: INDEX,
    component: Search,
    showFilter: false,
    showHeader: false,
  },
  {
    path: `${STANDARD}/:id${SECTION}/:section`,
    component: StandardSection,
    showHeader: true,
    showFilter: true,
  },
  {
    path: `${STANDARD}/:id`,
    component: Standard,
    showHeader: true,
    showFilter: true,
  },
  {
    path: `${CRE}/:id`,
    component: CommonRequirementEnumeration,
    showHeader: true,
    showFilter: false,
  },
  {
    path: `${GRAPH}/:id`,
    component: Graph,
    showHeader: true,
    showFilter: false,
  },
  {
    path: `${SEARCH}/:searchTerm`,
    component: SearchName,
    showHeader: true,
    showFilter: true,
  },
  {
    path: `${DEEPLINK}/:standardName`,
    component: Deeplink,
    showHeader: true,
    showFilter: false,
  }
];
