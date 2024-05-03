import { ReactNode } from 'react';

import {
  BROWSEROOT,
  CRE,
  EXPLORER,
  GAP_ANALYSIS,
  GRAPH,
  INDEX,
  SEARCH,
  SECTION,
  SECTION_ID,
  STANDARD,
} from './const';
import { CommonRequirementEnumeration, Graph, Search, Standard } from './pages';
import { BrowseRootCres } from './pages/BrowseRootCres/browseRootCres';
import { Chatbot } from './pages/chatbot/chatbot';
import { Explorer } from './pages/Explorer/explorer';
import { ExplorerCircles } from './pages/Explorer/visuals/circles/circles';
import { ExplorerForceGraph } from './pages/Explorer/visuals/force-graph/forceGraph';
import { GapAnalysis } from './pages/GapAnalysis/GapAnalysis';
import { MembershipRequired } from './pages/MembershipRequired/MembershipRequired';
import { SearchName } from './pages/Search/SearchName';
import { StandardSection } from './pages/Standard/StandardSection';

export interface IRoute {
  path: string;
  component: ReactNode | ReactNode[];
  showHeaderSearch: boolean;
  showFilter: boolean;
}

export const ROUTES: IRoute[] = [
  {
    path: INDEX,
    component: Search,
    showFilter: false,
    showHeaderSearch: false,
  },
  {
    path: GAP_ANALYSIS,
    component: GapAnalysis,
    showHeaderSearch: true,
    showFilter: false,
  },
  {
    path: `/node${STANDARD}/:id${SECTION}/:section`,
    component: StandardSection,
    showHeaderSearch: true,
    showFilter: true,
  },
  {
    path: `/node${STANDARD}/:id${SECTION_ID}/:sectionID`,
    component: StandardSection,
    showHeaderSearch: true,
    showFilter: true,
  },
  {
    path: `/node/:type/:id`,
    component: Standard,
    showHeaderSearch: true,
    showFilter: true,
  },
  {
    path: `${CRE}/:id`,
    component: CommonRequirementEnumeration,
    showHeaderSearch: true,
    showFilter: true,
  },
  {
    path: `${GRAPH}/:id`,
    component: Graph,
    showHeaderSearch: true,
    showFilter: false,
  },
  {
    path: `${SEARCH}/:searchTerm`,
    component: SearchName,
    showHeaderSearch: true,
    showFilter: true,
  },
  {
    path: `/chatbot`,
    component: Chatbot,
    showHeaderSearch: true,
    showFilter: false,
  },
  {
    path: '/members_required',
    component: MembershipRequired,
    showHeaderSearch: true,
    showFilter: false,
  },
  {
    path: `${BROWSEROOT}`,
    component: BrowseRootCres,
    showHeaderSearch: true,
    showFilter: false,
  },
  {
    path: `${EXPLORER}/circles`,
    component: ExplorerCircles,
    showHeaderSearch: true,
    showFilter: false,
  },
  {
    path: `${EXPLORER}/force_graph`,
    component: ExplorerForceGraph,
    showHeaderSearch: true,
    showFilter: false,
  },
  {
    path: `${EXPLORER}`,
    component: Explorer,
    showHeaderSearch: true,
    showFilter: false,
  },
];
