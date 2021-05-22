import './noRoute.scss';

import React, { FunctionComponent } from 'react';
import { Container, Header, Icon } from 'semantic-ui-react';

interface INoRouteProps {}

export const NoRoute: FunctionComponent<INoRouteProps> = () => (
  <Container className="no-route__container">
    <Header icon>
      <Icon name="search" />
      That page does not exist
    </Header>
  </Container>
);
