import React from 'react';

import { useCapabilities } from '../../hooks/useCapabilities';
import { Header, Router } from '../index';

export const MainContentArea = () => {
  const { capabilities, loading } = useCapabilities();

  if (loading || !capabilities) {
    return null; // or spinner
  }

  return (
    <>
      <Header capabilities={capabilities} />
      <Router capabilities={capabilities} />
    </>
  );
};
