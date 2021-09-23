import './app.scss';

import React from 'react';
import { Toaster } from 'react-hot-toast';
import { QueryClient, QueryClientProvider } from 'react-query';
import { BrowserRouter } from 'react-router-dom';

import { MainContentArea } from './scaffolding';

const queryClient = new QueryClient();

const App = () => (
  <div className="app">
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Toaster />
        <MainContentArea />
      </BrowserRouter>
    </QueryClientProvider>
  </div>
);

export default App;

