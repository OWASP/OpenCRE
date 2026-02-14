import React from 'react';
import { Route, Switch } from 'react-router-dom';

import { Capabilities } from '../../hooks/useCapabilities';
import { ROUTES } from '../../routes';
import { NoRoute } from '../index';

interface RouterProps {
  capabilities: Capabilities;
}

export const Router = ({ capabilities }: RouterProps) => {
  const routes = ROUTES(capabilities);

  return (
    <Switch>
      {routes.map(({ path, component: Component }) => {
        if (!Component) return null;

        const TypedComponent = Component as React.ElementType;

        return <Route key={path} path={path} exact={path === '/'} render={() => <TypedComponent />} />;
      })}
      <Route component={NoRoute} />
    </Switch>
  );
};
