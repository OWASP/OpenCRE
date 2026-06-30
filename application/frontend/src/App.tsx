import './app.scss';

import React from 'react';
import { Toaster } from 'react-hot-toast';
import { QueryClient, QueryClientProvider } from 'react-query';
import { BrowserRouter } from 'react-router-dom';

import { GlobalFilterState, filterContext } from './hooks/applyFilters';
import { MainContentArea } from './scaffolding';

const queryClient = new QueryClient();

const App = () => (
  <div className="app">
    <filterContext.Provider value={GlobalFilterState}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Toaster />
          <MainContentArea />
        </BrowserRouter>
      </QueryClientProvider>
    </filterContext.Provider>
  </div>
);

export default App;
