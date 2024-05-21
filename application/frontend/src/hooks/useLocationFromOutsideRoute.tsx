import { matchPath } from 'react-router';
import { useLocation } from 'react-router-dom';

import { ROUTES } from '../routes';

interface UseLocationFromOutsideRouteReturn {
  params: Record<string, string>;
  url: string;
  showFilter: boolean;
}

export const useLocationFromOutsideRoute = (): UseLocationFromOutsideRouteReturn => {
  // The current URL
  const { pathname } = useLocation();
  // The current ROUTE, from our URL
  const currentRoute = ROUTES.map(({ path, showFilter }) => ({
    ...matchPath(pathname, path),
    showFilter,
  })).find((matchedPath) => matchedPath?.isExact);
  return {
    params: currentRoute?.params || {},
    url: currentRoute?.url || '',
    showFilter: currentRoute?.showFilter || false,
  };
};
