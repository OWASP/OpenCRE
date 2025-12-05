import React, { FunctionComponent } from 'react';
import { Search } from 'lucide-react';

interface INoRouteProps { }

export const NoRoute: FunctionComponent<INoRouteProps> = () => (
  <div className="flex items-center justify-center h-screen bg-gray-50">
    <header className="flex flex-col items-center text-center p-8 bg-white rounded-lg shadow-lg">
      <Search className="w-16 h-16 text-gray-500 mb-4" />
      <h1 className="text-2xl font-semibold text-gray-700">
        That page does not exist
      </h1>
      <p className="text-gray-500 mt-2">
        We couldn't find the page you were looking for.
      </p>
    </header>
  </div>
);