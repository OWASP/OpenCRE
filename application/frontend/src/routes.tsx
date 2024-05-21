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
  showFilter: boolean;
}

export const ROUTES: IRoute[] = [
  {
    path: INDEX,
    component: Search,
    showFilter: false,
  },
  {
    path: GAP_ANALYSIS,
    component: GapAnalysis,
    showFilter: false,
  },
  {
    path: `/node${STANDARD}/:id${SECTION}/:section`,
    component: StandardSection,
    showFilter: true,
  },
  {
    path: `/node${STANDARD}/:id${SECTION_ID}/:sectionID`,
    component: StandardSection,
    showFilter: true,
  },
  {
    path: `/node/:type/:id`,
    component: Standard,
    showFilter: true,
  },
  {
    path: `${CRE}/:id`,
    component: CommonRequirementEnumeration,
    showFilter: true,
  },
  {
    path: `${GRAPH}/:id`,
    component: Graph,
    showFilter: false,
  },
  {
    path: `${SEARCH}/:searchTerm`,
    component: SearchName,
    showFilter: true,
  },
  {
    path: `/chatbot`,
    component: Chatbot,
    showFilter: false,
  },
  {
    path: '/members_required',
    component: MembershipRequired,
    showFilter: false,
  },
  {
    path: `${BROWSEROOT}`,
    component: BrowseRootCres,
    showFilter: false,
  },
  {
    path: `${EXPLORER}/circles`,
    component: ExplorerCircles,
    showFilter: false,
  },
  {
    path: `${EXPLORER}/force_graph`,
    component: ExplorerForceGraph,
    showFilter: false,
  },
  {
    path: `${EXPLORER}`,
    component: Explorer,
    showFilter: false,
  },
];
