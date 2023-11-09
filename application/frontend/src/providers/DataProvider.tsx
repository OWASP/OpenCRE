import axios from 'axios';
import React, { createContext, useContext, useEffect, useState } from 'react';
import { useQuery } from 'react-query';

import { TWO_DAYS_MILLISECONDS } from '../const';
import { useEnvironment } from '../hooks/useEnvironment';
import { Document, TreeDocument } from '../types';
import { getLocalStorageObject, setLocalStorageObject } from '../utils';
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
  const [dataLoading, setDataLoading] = useState<boolean>(false);
  const [dataStore, setDataStore] = useState<Record<string, TreeDocument>>(
    getLocalStorageObject(DATA_STORE_KEY) || {}
  );
  const [dataTree, setDataTree] = useState<TreeDocument[]>(getLocalStorageObject(DATA_TREE_KEY) || []);

  const getStoreKey = (doc: Document): string => {
    if (doc.doctype === 'CRE') return doc.id;
    return `${doc.name}-${doc.sectionID}`;
  };

  const buildTree = (doc: Document, keyPath: string[] = []): TreeDocument => {
    const selfKey = getStoreKey(doc);
    keyPath.push(selfKey);
    if (selfKey === '567-755') {
      console.log('BLA');
    }
    const storedDoc = structuredClone(dataStore[selfKey]);
    storedDoc.links = storedDoc.links
      .filter(
        (x) =>
          x.document && !keyPath.includes(getStoreKey(x.document)) && getStoreKey(x.document) in dataStore
      )
      .map((x) => ({ ltype: x.ltype, document: buildTree(x.document, keyPath) }));
    return storedDoc;
  };

  const getTreeQuery = useQuery(
    'root_cres',
    async () => {
      if (!dataTree.length && Object.keys(dataStore).length) {
        setDataLoading(true);
        try {
          const result = await axios.get(`${apiUrl}/root_cres`);
          const treeData = result.data.data.map((x) => buildTree(x));
          setLocalStorageObject(DATA_TREE_KEY, treeData, TWO_DAYS_MILLISECONDS);
          setDataTree(treeData);
        } catch (error) {
          console.error(error);
        }
      }
    },
    {
      retry: false,
      enabled: false,
      onSettled: () => {
        setDataLoading(false);
      },
    }
  );

  const getStoreQuery = useQuery(
    'everything',
    async () => {
      if (!Object.keys(dataStore).length) {
        try {
          setDataLoading(true);
          const result = await axios.get(`${apiUrl}/everything`);
          const data = result.data.data;
          if (data) {
            let store = {};
            data.forEach((x) => {
              store[getStoreKey(x)] = {
                links: [],
                displayName: getDocumentDisplayName(x),
                url: getInternalUrl(x),
                ...x,
              };
            });
            setLocalStorageObject(DATA_STORE_KEY, store, TWO_DAYS_MILLISECONDS);
            setDataStore(store);
          }
        } catch (error) {
          console.error(error);
        }
      }
    },
    {
      retry: false,
      enabled: false,
      onSettled: () => {
        setDataLoading(false);
      },
    }
  );
  useEffect(() => {
    setDataLoading(true);
    getStoreQuery.refetch();
  }, [dataTree]);

  useEffect(() => {
    setDataLoading(true);
    getTreeQuery.refetch();
  }, [dataStore, setDataStore]);

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
