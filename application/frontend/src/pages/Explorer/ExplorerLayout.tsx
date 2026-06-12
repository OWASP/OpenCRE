import React from 'react';

import { DataProvider } from '../../providers/DataProvider';

type ExplorerLayoutProps = {
  children: React.ReactNode;
};

export const ExplorerLayout = ({ children }: ExplorerLayoutProps) => <DataProvider>{children}</DataProvider>;

export function withExplorerLayout<P extends object>(Component: React.ComponentType<P>): React.FC<P> {
  const Wrapped = (props: P) => (
    <ExplorerLayout>
      <Component {...props} />
    </ExplorerLayout>
  );
  Wrapped.displayName = `ExplorerLayout(${Component.displayName || Component.name || 'Component'})`;
  return Wrapped;
}
