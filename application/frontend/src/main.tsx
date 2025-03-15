/* eslint-env browser */

import { Auth0Provider } from '@auth0/auth0-react';
import React from 'react';
import ReactDOM from 'react-dom';

import App from './App';

document.addEventListener('DOMContentLoaded', () => {
  ReactDOM.render(
    <Auth0Provider
      domain="dev-tvbmfb6izmzi0ml7.us.auth0.com"
      clientId="GukudojokWwUUKZBscg2HRr6ocR0KaE7"
      authorizationParams={{
        redirect_uri: 'http://localhost:9001/dashboard',
      }}
    >
      <App />
    </Auth0Provider>,
    document.getElementById('mount')
  );
});
