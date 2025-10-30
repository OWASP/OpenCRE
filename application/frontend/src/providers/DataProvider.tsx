import axios from 'axios';
import React, { createContext, useContext, useEffect, useState } from 'react';
import { useQuery } from 'react-query';

import { TWO_DAYS_MILLISECONDS } from '../const';
import { useEnvironment } from '../hooks/useEnvironment';
import { Document, TreeDocument } from '../types';
// Switched from localStorage utils to the new IndexedDB utils
import { getDbObject, setDbObject } from '../utils'; // Assumes utils/index.tsx is the entry point
import { getDocumentDisplayName, getInternalUrl } from '../utils/document';

const DATA_STORE_KEY = 'data-store',
  DATA_TREE_KEY = 'record-tree';

type DataContextValues = {
  dataLoading: boolean;
  dataStore: Record<string, TreeDocument>;
  dataTree: TreeDocument[];
  getStoreKey;
};

export const DataContext = createContext<DataContextValues | null>(null);

export const DataProvider = ({ children }: { children: React.ReactNode }) => {
  const { apiUrl } = useEnvironment();

  // Default loading to 'true' and initialize data states as empty
  const [dataLoading, setDataLoading] = useState<boolean>(true);
  const [dataStore, setDataStore] = useState<Record<string, TreeDocument>>({});
  const [dataTree, setDataTree] = useState<TreeDocument[]>([]);

  // Add new state to track if we have checked IndexedDB for cached data
  const [isHydrated, setIsHydrated] = useState<boolean>(false);

  const getStoreKey = (doc: Document): string => {
    if (doc.doctype === 'CRE') return doc.id;
    if (doc.doctype === 'Standard') return doc.name;
    return `${doc.name}-${doc.sectionID}-${doc.section}`;
  };

  const buildTree = (doc: Document, keyPath: string[] = []): TreeDocument => {
    const selfKey = getStoreKey(doc);
    keyPath.push(selfKey);
    const storedDoc = structuredClone(dataStore[selfKey]);
    const initialLinks = storedDoc.links;
    let creLinks = initialLinks.filter(
      (x) =>
        !!x.document && !keyPath.includes(getStoreKey(x.document)) && getStoreKey(x.document) in dataStore
    );
    creLinks = creLinks.filter((x) => x.ltype === 'Contains');
    creLinks = creLinks.map((x) => ({ ltype: x.ltype, document: buildTree(x.document, keyPath) }));
    storedDoc.links = [...creLinks];
    const standards = initialLinks.filter(
      (link) =>
        link.document && link.document.doctype === 'Standard' && !keyPath.includes(getStoreKey(link.document))
    );
    storedDoc.links = [...creLinks, ...standards];
    return storedDoc;
  };

  // New effect to asynchronously load data from IndexedDB on component mount
  useEffect(() => {
    const hydrateStateFromDb = async () => {
      console.log('Attempting to hydrate state from IndexedDB...');
      const cachedStore = await getDbObject(DATA_STORE_KEY);
      const cachedTree = await getDbObject(DATA_TREE_KEY);

      // If we found valid, unexpired data in the cache, load it into our state
      if (cachedStore && Object.keys(cachedStore).length > 0) {
        console.log('Cache hit. Hydrating state from IndexedDB.');
        setDataStore(cachedStore);
        setDataTree(cachedTree || []); // Use cached tree, or empty array as fallback
      } else {
        console.log('Cache miss or expired. Will fetch fresh data from API.');
      }

      // Mark hydration as complete. This will enable the API queries to run.
      setIsHydrated(true);
    };

    hydrateStateFromDb();
  }, []);

  const getTreeQuery = useQuery(
    'root_cres',
    async () => {
      if (!dataTree.length && Object.keys(dataStore).length) {
        try {
          const result = await axios.get(`${apiUrl}/root_cres`);
          const treeData = result.data.data.map((x) => buildTree(x));

          // Save to IndexedDB (async) instead of localStorage
          await setDbObject(DATA_TREE_KEY, treeData, TWO_DAYS_MILLISECONDS);

          setDataTree(treeData);
        } catch (error) {
          console.error(error);
        }
      }
    },
    {
      retry: false,
      // The query is disabled until hydration is complete
      enabled: isHydrated,
    }
  );

  const getStoreQuery = useQuery(
    'all_cres',
    async () => {
      if (!Object.keys(dataStore).length) {
        try {
          const result = await axios.get(`${apiUrl}/all_cres?page=1&per_page=1000`);
          let data = result.data.data;
          let store = {};

          if (data.length) {
            data.forEach((x) => {
              store[getStoreKey(x)] = {
                links: x.links,
                displayName: getDocumentDisplayName(x),
                url: getInternalUrl(x),
                ...x,
              };
            });

            // CHANGE 5: Save to IndexedDB (async) instead of localStorage
            await setDbObject(DATA_STORE_KEY, store, TWO_DAYS_MILLISECONDS);

            setDataStore(store);
            console.log('retrieved all cres');
          }
        } catch (error) {
          console.error('Could not retrieve CREs error:');
          console.error(error);
        }
      }
    },
    {
      retry: false,
      //  The query is disabled until hydration is complete
      enabled: isHydrated,
    }
  );

  useEffect(() => {
    //  Refined loading logic to account for the hydration phase
    if (!isHydrated) {
      setDataLoading(true);
    } else {
      setDataLoading(getStoreQuery.isLoading || getTreeQuery.isLoading);
    }
  }, [isHydrated, getStoreQuery.isLoading, getTreeQuery.isLoading]);

  //  Added 'isHydrated' guard to prevent premature API calls
  useEffect(() => {
    if (isHydrated) {
      getStoreQuery.refetch();
    }
  }, [dataTree, isHydrated]);

  useEffect(() => {
    if (isHydrated) {
      getTreeQuery.refetch();
    }
  }, [dataStore, isHydrated]); // Also removed setDataStore from deps to be safer

  return (
    <DataContext.Provider
      value={{
        dataLoading,
        dataStore,
        dataTree,
        getStoreKey,
      }}
    >
      {children}
    </DataContext.Provider>
  );
};

export const useDataStore = () => {
  const dataContext = useContext(DataContext);
  if (!dataContext) {
    throw new Error('useDataStore must be used within a DataProvider');
  }
  return dataContext;
};
