import './app.scss';

import React from 'react';
import { Toaster } from 'react-hot-toast';
import { QueryClient, QueryClientProvider } from 'react-query';
import { BrowserRouter, Route, Switch } from 'react-router-dom';

import { GlobalFilterState, filterContext } from './hooks/applyFilters';
import { Dashboard } from './pages/Dashboard/Dashboard';
import { DataProvider } from './providers/DataProvider';
import { MainContentArea } from './scaffolding';

const queryClient = new QueryClient();

const App = () => (
  <div className="app">
    <filterContext.Provider value={GlobalFilterState}>
      <QueryClientProvider client={queryClient}>
        <DataProvider>
          <BrowserRouter>
            <Toaster />

            <MainContentArea />
            <Switch>
              <Route path="/dashboard" component={Dashboard} />
            </Switch>
          </BrowserRouter>
        </DataProvider>
      </QueryClientProvider>
    </filterContext.Provider>
  </div>
);

export default App;
