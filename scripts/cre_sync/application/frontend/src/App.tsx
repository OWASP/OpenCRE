import './app.scss';

import React, { FunctionComponent } from 'react';
import { Toaster } from 'react-hot-toast';
import { QueryClient, QueryClientProvider } from 'react-query';
import { BrowserRouter } from 'react-router-dom';

import { MainContentArea } from './scaffolding';

const queryClient = new QueryClient();

interface IAppProps {}

const App: FunctionComponent<IAppProps> = () => {
  return (
    <div className="app">
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Toaster />
          <MainContentArea />
        </BrowserRouter>
      </QueryClientProvider>
    </div>
  );
};

export default App;
