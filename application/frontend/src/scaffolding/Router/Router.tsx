import React from 'react';
import { Route, Switch } from 'react-router-dom';

import { ROUTES } from '../../routes';
import { NoRoute } from '../index';

export const Router = () => (
  <Switch>
    {ROUTES.map(({ path, component: Component }) => {
      if (!Component) {
        return null;
      }
      const TypedComponent = Component as React.ElementType;

      return <Route key={path} path={path} exact={path === '/'} render={() => <TypedComponent />} />;
    })}
    <Route component={NoRoute} />
  </Switch>
);
