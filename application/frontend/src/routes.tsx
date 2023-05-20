import { ReactNode } from 'react';

import { BROWSEROOT, CRE, DEEPLINK, GRAPH, INDEX, SEARCH, SECTION, SECTION_ID, STANDARD } from './const';
import { CommonRequirementEnumeration, Graph, Search, Standard } from './pages';
import { BrowseRootCres } from './pages/BrowseRootCres/browseRootCres';
import { Chatbot } from './pages/chatbot/chatbot';
import { Deeplink } from './pages/Deeplink/Deeplink';
import { SearchName } from './pages/Search/SearchName';
import { StandardSection } from './pages/Standard/StandardSection';

export interface IRoute {
  path: string;
  component: ReactNode | ReactNode[];
  showHeader: boolean;
  showFilter: boolean;
}

export const ROUTES: IRoute[] = [
  {
    path: INDEX,
    component: Search,
    showFilter: false,
    showHeader: false,
  },
  {
    path: `/node${STANDARD}/:id${SECTION}/:section`,
    component: StandardSection,
    showHeader: true,
    showFilter: true,
  },
  {
    path: `/node${STANDARD}/:id${SECTION_ID}/:sectionID`,
    component: StandardSection,
    showHeader: true,
    showFilter: true,
  },
  {
    path: `/node/:type/:id`,
    component: Standard,
    showHeader: true,
    showFilter: true,
  },
  {
    path: `${CRE}/:id`,
    component: CommonRequirementEnumeration,
    showHeader: true,
    showFilter: true,
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
    path: `${DEEPLINK}/node/:type/:nodeName/section/:section`,
    component: Deeplink,
    showHeader: true,
    showFilter: false,
  },
  {
    path: `${DEEPLINK}/node/:type/:nodeName/section/:section/subsection/:subsection`,
    component: Deeplink,
    showHeader: true,
    showFilter: false,
  },
  {
    path: `${DEEPLINK}/node/:type/:nodeName/tooltype/:tooltype`,
    component: Deeplink,
    showHeader: true,
    showFilter: false,
  },
  {
    path: `${DEEPLINK}/node/:type/:nodeName`,
    component: Deeplink,
    showHeader: true,
    showFilter: false,
  },
  {
    path: `${DEEPLINK}/:nodeName`,
    component: Deeplink,
    showHeader: true,
    showFilter: false,
  },
  {
    path: `/chatbot`,
    component: Chatbot,
    showHeader: true,
    showFilter: false,
  },
  {
    path: `${BROWSEROOT}`,
    component: BrowseRootCres,
    showHeader: true,
    showFilter: false,
  },
];
