import React from 'react';
import { Route, Switch } from 'react-router-dom';

import { ROUTES } from '../../routes';
import { NoRoute } from '../index';

export const Router = () => (
  <Switch>
    {ROUTES.map(({ path, component }) => (
      <Route key={path} path={path} exact={path === '/'} component={component} />
    ))}
    <Route component={NoRoute} />
  </Switch>
);
