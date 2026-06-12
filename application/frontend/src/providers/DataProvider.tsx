import axios from 'axios';
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';

import { EXPLORER_CRE_PAGE_SIZE, TWO_DAYS_MILLISECONDS } from '../const';
import { useEnvironment } from '../hooks/useEnvironment';
import { Document, TreeDocument } from '../types';
import { getDbObject, setDbObject } from '../utils';
import { getInternalUrl, getTopicDisplayName } from '../utils/document';

const DATA_STORE_CACHE_KEY = 'data-store-v2';
const DATA_TREE_KEY = 'record-tree';

type DataStoreCache = {
  store: Record<string, TreeDocument>;
  loadedPages: number;
  totalPages: number;
  isFullStoreLoaded: boolean;
};

const isDataStoreCache = (value: unknown): value is DataStoreCache => {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const record = value as Record<string, unknown>;
  return 'store' in record && 'loadedPages' in record && 'totalPages' in record;
};

type DataContextValues = {
  dataLoading: boolean;
  dataStore: Record<string, TreeDocument>;
  dataTree: TreeDocument[];
  getStoreKey: (doc: Document) => string;
  hasMore: boolean;
  isLoadingMore: boolean;
  fullLoadProgress: string | null;
  loadNextPage: () => Promise<void>;
  ensureFullExplorerData: () => Promise<void>;
};

export const DataContext = createContext<DataContextValues | null>(null);

const docToStoreEntry = (doc: Document): TreeDocument =>
  ({
    links: doc.links ?? [],
    displayName: getTopicDisplayName(doc),
    url: getInternalUrl(doc),
    ...doc,
  } as TreeDocument);

const mergeDocsIntoStore = (
  docs: Document[],
  store: Record<string, TreeDocument>,
  getStoreKey: (doc: Document) => string
): Record<string, TreeDocument> => {
  const nextStore = { ...store };
  docs.forEach((doc) => {
    nextStore[getStoreKey(doc)] = docToStoreEntry(doc);
  });
  return nextStore;
};

export const DataProvider = ({ children }: { children: React.ReactNode }) => {
  const { apiUrl } = useEnvironment();

  const [dataLoading, setDataLoading] = useState<boolean>(true);
  const [dataStore, setDataStore] = useState<Record<string, TreeDocument>>({});
  const [dataTree, setDataTree] = useState<TreeDocument[]>([]);
  const [isHydrated, setIsHydrated] = useState<boolean>(false);
  const [loadedPages, setLoadedPages] = useState<number>(0);
  const [totalPages, setTotalPages] = useState<number>(0);
  const [isLoadingMore, setIsLoadingMore] = useState<boolean>(false);
  const [isFullStoreLoaded, setIsFullStoreLoaded] = useState<boolean>(false);
  const [fullLoadProgress, setFullLoadProgress] = useState<string | null>(null);

  const dataStoreRef = useRef(dataStore);
  const loadedPagesRef = useRef(loadedPages);
  const totalPagesRef = useRef(totalPages);
  const isFullStoreLoadedRef = useRef(isFullStoreLoaded);
  const loadingPageRef = useRef(false);
  const fullLoadRef = useRef<Promise<void> | null>(null);
  const bootstrapDoneRef = useRef(false);

  useEffect(() => {
    dataStoreRef.current = dataStore;
  }, [dataStore]);
  useEffect(() => {
    loadedPagesRef.current = loadedPages;
  }, [loadedPages]);
  useEffect(() => {
    totalPagesRef.current = totalPages;
  }, [totalPages]);
  useEffect(() => {
    isFullStoreLoadedRef.current = isFullStoreLoaded;
  }, [isFullStoreLoaded]);

  const getStoreKey = useCallback((doc: Document): string => {
    if (doc.doctype === 'CRE') return doc.id;
    if (doc.doctype === 'Standard') return doc.name;
    return `${doc.name}-${doc.sectionID}-${doc.section}`;
  }, []);

  const buildTree = useCallback(
    (doc: Document, store: Record<string, TreeDocument>, keyPath: string[] = []): TreeDocument => {
      const selfKey = getStoreKey(doc);
      keyPath.push(selfKey);
      const storedDoc = structuredClone(store[selfKey] ?? doc);
      const initialLinks = storedDoc.links || [];
      let creLinks = initialLinks.filter(
        (x) => !!x.document && !keyPath.includes(getStoreKey(x.document)) && getStoreKey(x.document) in store
      );
      creLinks = creLinks.filter((x) => x.ltype === 'Contains');
      creLinks = creLinks.map((x) => ({
        ltype: x.ltype,
        document: buildTree(x.document, store, keyPath),
      }));
      storedDoc.links = [...creLinks];
      const standards = initialLinks.filter(
        (link) =>
          link.document &&
          link.document.doctype === 'Standard' &&
          !keyPath.includes(getStoreKey(link.document))
      );
      storedDoc.links = [...creLinks, ...standards];
      return storedDoc;
    },
    [getStoreKey]
  );

  const persistCache = useCallback(
    async (
      store: Record<string, TreeDocument>,
      pagesLoaded: number,
      pagesTotal: number,
      fullLoaded: boolean,
      tree?: TreeDocument[]
    ) => {
      const payload: DataStoreCache = {
        store,
        loadedPages: pagesLoaded,
        totalPages: pagesTotal,
        isFullStoreLoaded: fullLoaded,
      };
      await setDbObject(DATA_STORE_CACHE_KEY, payload, TWO_DAYS_MILLISECONDS);
      if (tree) {
        await setDbObject(DATA_TREE_KEY, tree, TWO_DAYS_MILLISECONDS);
      }
    },
    []
  );

  const rebuildDataTree = useCallback(
    async (store: Record<string, TreeDocument>) => {
      if (!Object.keys(store).length) {
        setDataTree([]);
        return [];
      }
      const result = await axios.get(`${apiUrl}/root_cres`);
      const treeData = result.data.data.map((x: Document) => buildTree(x, store));
      setDataTree(treeData);
      return treeData;
    },
    [apiUrl, buildTree]
  );

  const loadPage = useCallback(
    async (page: number): Promise<Record<string, TreeDocument>> => {
      if (loadingPageRef.current) {
        return dataStoreRef.current;
      }
      loadingPageRef.current = true;
      setIsLoadingMore(true);
      try {
        const result = await axios.get(`${apiUrl}/all_cres`, {
          params: { page, per_page: EXPLORER_CRE_PAGE_SIZE },
        });
        const docs: Document[] = result.data.data || [];
        const pagesTotal = Number(result.data.total_pages) || 1;
        const nextStore = mergeDocsIntoStore(docs, dataStoreRef.current, getStoreKey);
        const pagesLoaded = page;

        dataStoreRef.current = nextStore;
        setDataStore(nextStore);
        setLoadedPages(pagesLoaded);
        setTotalPages(pagesTotal);
        loadedPagesRef.current = pagesLoaded;
        totalPagesRef.current = pagesTotal;

        const fullLoaded = pagesLoaded >= pagesTotal;
        if (fullLoaded) {
          isFullStoreLoadedRef.current = true;
          setIsFullStoreLoaded(true);
        }

        const treeData = await rebuildDataTree(nextStore);
        await persistCache(nextStore, pagesLoaded, pagesTotal, fullLoaded, treeData);

        return nextStore;
      } finally {
        loadingPageRef.current = false;
        setIsLoadingMore(false);
      }
    },
    [apiUrl, getStoreKey, persistCache, rebuildDataTree]
  );

  const loadNextPage = useCallback(async () => {
    if (isFullStoreLoadedRef.current) {
      return;
    }
    const nextPage = loadedPagesRef.current + 1;
    if (nextPage > totalPagesRef.current && totalPagesRef.current > 0) {
      return;
    }
    await loadPage(nextPage);
  }, [loadPage]);

  const ensureFullExplorerData = useCallback(async () => {
    if (fullLoadRef.current) {
      return fullLoadRef.current;
    }

    fullLoadRef.current = (async () => {
      setFullLoadProgress(null);
      if (!loadedPagesRef.current) {
        await loadPage(1);
      }
      while (loadedPagesRef.current < totalPagesRef.current) {
        setFullLoadProgress(`${loadedPagesRef.current}/${totalPagesRef.current}`);
        await loadPage(loadedPagesRef.current + 1);
      }
      isFullStoreLoadedRef.current = true;
      setIsFullStoreLoaded(true);
      setFullLoadProgress(null);
      await rebuildDataTree(dataStoreRef.current);
    })();

    try {
      await fullLoadRef.current;
    } finally {
      fullLoadRef.current = null;
    }
  }, [loadPage, rebuildDataTree]);

  useEffect(() => {
    const hydrateStateFromDb = async () => {
      const cached = await getDbObject(DATA_STORE_CACHE_KEY);
      const cachedTree = await getDbObject(DATA_TREE_KEY);

      if (isDataStoreCache(cached) && Object.keys(cached.store).length > 0) {
        dataStoreRef.current = cached.store;
        setDataStore(cached.store);
        setLoadedPages(cached.loadedPages);
        setTotalPages(cached.totalPages);
        loadedPagesRef.current = cached.loadedPages;
        totalPagesRef.current = cached.totalPages;
        isFullStoreLoadedRef.current = cached.isFullStoreLoaded;
        setIsFullStoreLoaded(cached.isFullStoreLoaded);
        if (cachedTree?.length) {
          setDataTree(cachedTree);
        }
      } else if (cached && typeof cached === 'object' && !isDataStoreCache(cached)) {
        const legacyStore = cached as Record<string, TreeDocument>;
        dataStoreRef.current = legacyStore;
        setDataStore(legacyStore);
        isFullStoreLoadedRef.current = true;
        setIsFullStoreLoaded(true);
        if (cachedTree?.length) {
          setDataTree(cachedTree);
        }
      }

      setIsHydrated(true);
    };

    hydrateStateFromDb();
  }, []);

  useEffect(() => {
    if (!isHydrated || bootstrapDoneRef.current) {
      return;
    }
    bootstrapDoneRef.current = true;

    const bootstrap = async () => {
      setDataLoading(true);
      try {
        if (loadedPagesRef.current === 0 && !isFullStoreLoadedRef.current) {
          await loadPage(1);
        } else if (Object.keys(dataStoreRef.current).length) {
          await rebuildDataTree(dataStoreRef.current);
        }
      } finally {
        setDataLoading(false);
      }
    };

    bootstrap();
  }, [isHydrated, loadPage, rebuildDataTree]);

  useEffect(() => {
    if (!isHydrated || isFullStoreLoaded || loadedPages === 0) {
      return;
    }

    const idleCallback = (window as Window & { requestIdleCallback?: Function }).requestIdleCallback;
    const cancelIdleCallback = (window as Window & { cancelIdleCallback?: Function }).cancelIdleCallback;

    const prefetch = () => {
      if (!isFullStoreLoadedRef.current && loadedPagesRef.current < totalPagesRef.current) {
        loadNextPage();
      }
    };

    if (idleCallback) {
      const handle = idleCallback(prefetch, { timeout: 4000 });
      return () => cancelIdleCallback?.(handle);
    }

    const timer = window.setTimeout(prefetch, 2000);
    return () => window.clearTimeout(timer);
  }, [isHydrated, isFullStoreLoaded, loadedPages, totalPages, loadNextPage]);

  const hasMore = !isFullStoreLoaded && loadedPages > 0 && loadedPages < totalPages;

  return (
    <DataContext.Provider
      value={{
        dataLoading,
        dataStore,
        dataTree,
        getStoreKey,
        hasMore,
        isLoadingMore,
        fullLoadProgress,
        loadNextPage,
        ensureFullExplorerData,
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
