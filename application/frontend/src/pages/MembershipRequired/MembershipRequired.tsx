import './MembershipRequired.scss';

import React from 'react';
import { Button, Header } from 'semantic-ui-react';

export const MembershipRequired = () => {
  return (
    <div className="membership-required">
      <Header as="h1" className="membership-required__heading">
        OWASP Membership Required
      </Header>
      <p>A OWASP Membership account is needed to login</p>
      <Button primary href="https://owasp.org/membership/">
        Sign up
      </Button>
    </div>
  );
};
