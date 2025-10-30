import { DBSchema, openDB } from 'idb';
export { groupLinksByType, LinksByType, getDocumentDisplayName } from './document';

const DB_NAME = 'DataCacheDB';
const STORE_NAME = 'KeyValStore';
const DB_VERSION = 1;

//  the database schema for type safety
interface CacheDB extends DBSchema {
  [STORE_NAME]: {
    key: string;
    value: {
      value: any;
      expiry: number;
    };
  };
}

// Initialize the database connection promise
const dbPromise = openDB<CacheDB>(DB_NAME, DB_VERSION, {
  upgrade(db) {
    // This store will hold key-value pairs, just like localStorage
    db.createObjectStore(STORE_NAME);
  },
});

export const getDbObject = async (key: string): Promise<any | null> => {
  const db = await dbPromise;
  const item = await db.get(STORE_NAME, key);

  if (!item) {
    return null;
  }

  // Check expiry
  if (Date.now() > item.expiry) {
    db.delete(STORE_NAME, key);
    return null;
  }

  return item.value;
};

/**
 * Stores an item in IndexedDB with an expiry timestamp.
 */
export const setDbObject = async (key: string, value: any, ttl: number): Promise<void> => {
  const db = await dbPromise;
  const expiry = Date.now() + ttl;
  const item = {
    value,
    expiry,
  };
  await db.put(STORE_NAME, item, key);
};
