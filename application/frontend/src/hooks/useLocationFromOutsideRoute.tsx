import { matchPath } from 'react-router';
import { useLocation } from 'react-router-dom';

import { ROUTES } from '../routes';

interface UseLocationFromOutsideRouteReturn {
  params: Record<string, string>;
  url: string;
  showHeader: boolean;
  showFilter: boolean;
}

export const useLocationFromOutsideRoute = (): UseLocationFromOutsideRouteReturn => {
  // The current URL
  const { pathname } = useLocation();
  // The current ROUTE, from our URL
  const currentRoute = ROUTES.map(({ path, showHeader, showFilter }) => ({
    ...matchPath(pathname, path),
    showHeader,
    showFilter,
  })).find((matchedPath) => matchedPath?.isExact);
  return {
    params: currentRoute?.params || {},
    url: currentRoute?.url || '',
    showHeader: currentRoute?.showHeader || false,
    showFilter: currentRoute?.showFilter || false,
  };
};
